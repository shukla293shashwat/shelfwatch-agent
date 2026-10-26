// The browser sends photos to FastAPI and displays the returned evidence.
const currentInput = document.getElementById("current");
const referenceInput = document.getElementById("reference");
const resultRoot = document.getElementById("result");
const errorRoot = document.getElementById("error");
const analyzeButton = document.getElementById("analyze");
const demoButton = document.getElementById("demo");
const realDemoButton = document.getElementById("real-demo");

function authHeaders() {
  const code = document.getElementById("access-code").value.trim();
  return code ? { Authorization: `Bearer ${code}` } : {};
}

function textElement(tag, text, className) {
  const element = document.createElement(tag);
  element.textContent = text;
  if (className) element.className = className;
  return element;
}

function attachPreview(input, targetId) {
  const preview = document.getElementById(targetId);

  input.addEventListener("change", () => {
    if (preview.dataset.url) URL.revokeObjectURL(preview.dataset.url);
    const file = input.files?.[0];

    if (!file) {
      preview.removeAttribute("src");
      preview.style.display = "none";
      return;
    }

    const url = URL.createObjectURL(file);
    preview.dataset.url = url;
    preview.src = url;
    preview.style.display = "block";
  });
}

function renderCells(cells, columns) {
  const grid = document.createElement("div");
  grid.className = "grid";
  grid.style.gridTemplateColumns = `repeat(${columns}, minmax(0, 1fr))`;
  grid.setAttribute("aria-label", "Cell-by-cell inspection results");

  for (const item of cells) {
    const cell = document.createElement("div");
    cell.className = `cell ${item.status}`;
    cell.title = `${item.label}: ${item.status}; score ${item.score}`;
    cell.append(
      textElement("span", `R${item.row + 1} C${item.col + 1}`),
      textElement("small", item.status.toUpperCase()),
    );
    grid.append(cell);
  }

  return grid;
}

function renderTrace(trace) {
  const details = document.createElement("details");
  details.className = "trace";
  details.open = true;
  details.append(textElement("summary", "Agent decision trace"));
  const list = document.createElement("ol");

  for (const step of trace) {
    const line = document.createElement("li");
    const label = `Step ${step.step}: ${(step.event || "").replaceAll("_", " ")}`;
    line.append(
      textElement("b", label),
      document.createTextNode(` — ${step.observation || ""}`),
    );

    if (step.tool) {
      line.append(document.createElement("br"), `Tool: ${step.tool}`);
    }
    if (step.decision) {
      line.append(document.createElement("br"), `Next action: ${step.decision}`);
    }
    list.append(line);
  }

  details.append(list);
  return details;
}

function renderApproval(orderId) {
  const gate = document.createElement("div");
  gate.className = "approval";
  gate.append(textElement(
    "p",
    "Review the draft and uncertain cells before approving. Approval is recorded locally; no order is transmitted.",
  ));

  const button = textElement("button", "Approve draft locally", "button primary");
  button.type = "button";
  button.addEventListener("click", () => approveDraft(orderId, button, gate));
  gate.append(button);
  return gate;
}

function renderResult(data) {
  resultRoot.className = "result-body";
  resultRoot.replaceChildren();

  const heading = document.createElement("div");
  heading.className = "result-top";
  heading.append(
    textElement("h3", data.status.replaceAll("_", " ")),
    textElement(
      "span",
      `OpenCV ${data.opencv_version} · alignment ${Math.round(data.confidence * 100)}%`,
      "pill",
    ),
  );
  resultRoot.append(heading, textElement("p", data.message, "result-message"));
  resultRoot.append(textElement("p", `${data.regions?.length || 0} local change regions · ${data.gaps.length} affected cells · ${data.uncertain.length} review cells`, "hint"));

  if (data.reference_source) {
    resultRoot.append(textElement("p", `Reference: ${data.reference_source}`, "hint"));
  }
  if (data.overlay) {
    const image = document.createElement("img");
    image.className = "overlay";
    image.alt = "Shelf cells marked as stocked, likely missing, or requiring review";
    image.src = `data:image/jpeg;base64,${data.overlay}`;
    resultRoot.append(image);
  }
  if (data.cells?.length) resultRoot.append(renderCells(data.cells, data.cols || 6));
  if (data.order_id) resultRoot.append(renderApproval(data.order_id));
  if (data.trace?.length) resultRoot.append(renderTrace(data.trace));
}

async function approveDraft(orderId, button, gate) {
  button.disabled = true;
  button.textContent = "Recording approval…";

  try {
    const response = await fetch(`/approve/${encodeURIComponent(orderId)}`, {
      method: "POST",
      headers: authHeaders(),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Approval could not be recorded.");
    gate.replaceChildren(textElement("div", data.message, "approval-done"));
  } catch (error) {
    button.disabled = false;
    button.textContent = "Approve draft locally";
    gate.append(textElement("p", error.message, "error"));
  }
}

async function inspectShelf(url, form) {
  errorRoot.textContent = "";
  analyzeButton.disabled = true;
  demoButton.disabled = true;
  realDemoButton.disabled = true;
  resultRoot.className = "empty";
  resultRoot.replaceChildren(textElement("p", "Comparing shelf images with OpenCV 5…"));

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: authHeaders(),
      ...(form ? { body: form } : {}),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Analysis failed.");
    renderResult(data);
  } catch (error) {
    resultRoot.className = "empty";
    resultRoot.replaceChildren(
      textElement("h3", "Inspection could not be completed"),
      textElement("p", error.message),
    );
    errorRoot.textContent = "Check the photo and try again.";
  } finally {
    analyzeButton.disabled = false;
    demoButton.disabled = false;
    realDemoButton.disabled = false;
  }
}

attachPreview(currentInput, "current-preview");
attachPreview(referenceInput, "reference-preview");

analyzeButton.addEventListener("click", () => {
  const photo = currentInput.files?.[0];
  if (!photo) {
    errorRoot.textContent = "Choose a current shelf photo, or use the synthetic demo.";
    currentInput.focus();
    return;
  }

  const selection = selectedArea();
  if (!(selection[0] < selection[2] && selection[1] < selection[3])) {
    errorRoot.textContent = "Choose a shelf rectangle with positive width and height.";
    return;
  }
  const form = new FormData();
  form.append("roi", JSON.stringify(selection));
  form.append("rows", document.getElementById("grid-rows").value);
  form.append("cols", document.getElementById("grid-cols").value);
  form.append("current", photo);
  const reference = referenceInput.files?.[0];
  if (reference) form.append("reference", reference);
  inspectShelf("/analyze", form);
});

demoButton.addEventListener("click", () => inspectShelf("/demo"));
realDemoButton.addEventListener("click", () => inspectShelf("/demo/real-one"));

fetch("/health")
  .then((response) => response.json())
  .then((data) => {
    const ready = data.ok && data.opencv5;
    document.getElementById("access-field").hidden = !data.auth_required;
    if (data.ephemeral_state) document.getElementById("hosting-note").textContent = "This demo has no backup for saved drafts.";
    document.getElementById("api-status").textContent = ready
      ? `OpenCV ${data.opencv_version} ready`
      : `OpenCV 5 required · found ${data.opencv_version}`;
  })
  .catch(() => {
    document.getElementById("api-status").textContent = "API unavailable";
  });


// Selection is normalized, so resizing the preview does not change the shelf area.
const roiCanvas = document.getElementById("roi-canvas");
const referencePreview = document.getElementById("reference-preview");
const roiInputs = ["left", "top", "right", "bottom"].map((edge) => document.getElementById(`roi-${edge}`));
let dragStart = null;

function selectedArea() {
  return roiInputs.map((input) => Math.min(100, Math.max(0, Number(input.value))) / 100);
}

function drawSelection() {
  if (!referencePreview.naturalWidth) return;
  const context = roiCanvas.getContext("2d");
  context.clearRect(0, 0, roiCanvas.width, roiCanvas.height);
  context.drawImage(referencePreview, 0, 0, roiCanvas.width, roiCanvas.height);
  const [left, top, right, bottom] = selectedArea();
  if (left >= right || top >= bottom) return;
  context.fillStyle = "rgba(0, 0, 0, 0.42)";
  context.fillRect(0, 0, roiCanvas.width, roiCanvas.height);
  const x = left * roiCanvas.width;
  const y = top * roiCanvas.height;
  const width = (right - left) * roiCanvas.width;
  const height = (bottom - top) * roiCanvas.height;
  context.drawImage(referencePreview,
    left * referencePreview.naturalWidth, top * referencePreview.naturalHeight,
    (right - left) * referencePreview.naturalWidth, (bottom - top) * referencePreview.naturalHeight,
    x, y, width, height);
  context.strokeStyle = "#7de0ad";
  context.lineWidth = 3;
  context.strokeRect(x, y, width, height);
}

function setSelection(values) {
  roiInputs.forEach((input, index) => { input.value = Math.round(values[index] * 100); });
  drawSelection();
}

function pointerPosition(event) {
  const box = roiCanvas.getBoundingClientRect();
  return [Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)),
          Math.max(0, Math.min(1, (event.clientY - box.top) / box.height))];
}

referencePreview.addEventListener("load", () => {
  const scale = Math.min(1, 900 / referencePreview.naturalWidth);
  roiCanvas.width = Math.round(referencePreview.naturalWidth * scale);
  roiCanvas.height = Math.round(referencePreview.naturalHeight * scale);
  roiCanvas.hidden = false;
  referencePreview.style.display = "none";
  setSelection([0, 0, 1, 1]);
});
referenceInput.addEventListener("change", () => {
  if (!referenceInput.files?.length) roiCanvas.hidden = true;
});
roiInputs.forEach((input) => input.addEventListener("input", drawSelection));
document.getElementById("roi-reset").addEventListener("click", () => setSelection([0, 0, 1, 1]));
roiCanvas.addEventListener("pointerdown", (event) => {
  dragStart = pointerPosition(event);
  roiCanvas.setPointerCapture(event.pointerId);
});
roiCanvas.addEventListener("pointermove", (event) => {
  if (!dragStart) return;
  const end = pointerPosition(event);
  setSelection([Math.min(dragStart[0], end[0]), Math.min(dragStart[1], end[1]),
                Math.max(dragStart[0], end[0]), Math.max(dragStart[1], end[1])]);
});
roiCanvas.addEventListener("pointerup", () => { dragStart = null; });
roiCanvas.addEventListener("pointercancel", () => { dragStart = null; });
