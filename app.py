"""ShelfWatch Agent demo API and accessible single-page interface."""
import base64
import json
import os
import threading
from contextlib import asynccontextmanager
from pathlib import Path

os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", "24000000")

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from shelfwatch import agent, storage, vision
from shelfwatch.operations import COUNTERS, Guardrails

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
DEFAULT_REFERENCE = SAMPLES / "reference.jpg"
DEMO_CURRENT = SAMPLES / "current_3_missing.jpg"
MAX_UPLOAD_BYTES = 12 * 1024 * 1024
MAX_IMAGE_DIMENSION = max(320, min(1600, int(os.getenv("SHELFWATCH_MAX_IMAGE_DIMENSION", "1600"))))
MAX_IMAGE_PIXELS = 24_000_000
# Default reporting grid; the selected shelf area can use another layout.
ROWS, COLS = 3, 6

ANALYSIS_SLOTS = threading.BoundedSemaphore(max(1, min(2, int(os.getenv("SHELFWATCH_MAX_ANALYSES", "2")))))
cv2.setNumThreads(max(1, min(4, int(os.getenv("SHELFWATCH_CV_THREADS", "2")))))


@asynccontextmanager
async def lifespan(app):
    if not cv2.__version__.startswith("5."):
        raise RuntimeError("ShelfWatch requires OpenCV 5.")
    if os.getenv("SHELFWATCH_PUBLIC") == "1" and len(os.getenv("SHELFWATCH_TOKEN", "")) < 24:
        raise RuntimeError("Public mode requires an access code of at least 24 characters.")
    with storage.connect():
        pass
    yield


app = FastAPI(
    lifespan=lifespan,
    title="ShelfWatch Agent",
    description="OpenCV 5 shelf inspection with active reinspection and human-approved restock drafts.",
    version="2.0.0",
)

app.add_middleware(Guardrails)
app.mount("/examples", StaticFiles(directory=SAMPLES), name="examples")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")


def _normalize(img: np.ndarray) -> np.ndarray:
    height, width = img.shape[:2]
    if height * width > MAX_IMAGE_PIXELS:
        raise HTTPException(413, "Image dimensions are too large. Use a photo under 24 megapixels.")
    scale = min(1.0, MAX_IMAGE_DIMENSION / max(height, width))
    if scale < 1.0:
        img = cv2.resize(img, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
    return img


def _decode(data: bytes, name: str) -> np.ndarray:
    if not data:
        raise HTTPException(400, f"The {name} upload is empty.")
    try:
        img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    except cv2.error as error:
        raise HTTPException(400, f"Could not decode {name}. Use a JPEG, PNG or WebP under 24 megapixels.") from error
    if img is None:
        raise HTTPException(400, f"Could not decode {name}. Upload a JPEG, PNG, or WebP image.")
    return _normalize(img)


def _read_upload(upload: UploadFile, name: str) -> np.ndarray:
    data = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{name.title()} image must be 12 MB or smaller.")
    return _decode(data, name)


def _analyze(current: np.ndarray, reference: np.ndarray, reference_source: str, roi=None, rows=ROWS, cols=COLS) -> dict:
    if not 1 <= rows <= 12 or not 1 <= cols <= 24:
        raise HTTPException(400, "Choose 1–12 rows and 1–24 slots per row.")
    if not ANALYSIS_SLOTS.acquire(blocking=False):
        raise HTTPException(429, "Two inspections are already running. Please try again shortly.")
    try:
        result = agent.run(reference, current, rows, cols, roi=roi)
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    except cv2.error as error:
        raise HTTPException(422, "OpenCV could not inspect these images. Use a clear, well-lit shelf photo.") from error
    finally:
        ANALYSIS_SLOTS.release()
    COUNTERS["analyses"] += 1
    COUNTERS["result_" + result["status"]] += 1

    overlay_b64 = None
    if result["aligned"] is not None:
        annotated = vision.overlay(result["aligned"], result["results"], rows, cols, result["roi"], result["regions"])
        encoded, buffer = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 88])
        if encoded:
            overlay_b64 = base64.b64encode(buffer).decode("ascii")

    cells = []
    for (row, col), cell in sorted(result["results"].items()):
        cells.append({
            "row": row,
            "col": col,
            "label": f"Row {row + 1}, slot {col + 1}",
            **cell,
        })

    return {
        "status": result["status"],
        "message": result["message"],
        "order_id": result.get("order_id"),
        "confidence": round(float(result["confidence"]), 3),
        "opencv_version": cv2.__version__,
        "reference_source": reference_source,
        "gaps": [list(cell) for cell in result["gaps"]],
        "uncertain": [list(cell) for cell in result["uncertain"]],
        "cells": cells,
        "regions": result["regions"],
        "roi": result["roi"],
        "rows": rows,
        "cols": cols,
        "trace": result["trace"],
        "overlay": overlay_b64,
    }


@app.get("/health")
def health():
    major = int(cv2.__version__.split(".", 1)[0])
    return {"ok": major == 5, "version": "2.0.0", "opencv_version": cv2.__version__, "opencv5": major == 5, "auth_required": bool(os.getenv("SHELFWATCH_TOKEN")), "approval_storage": "sqlite", "ephemeral_state": os.getenv("SHELFWATCH_EPHEMERAL_STATE") == "1"}


@app.post("/analyze")
def analyze(current: UploadFile = File(...), reference: UploadFile | None = File(default=None), roi: str | None = Form(default=None), rows: int = Form(default=ROWS), cols: int = Form(default=COLS)):
    current_img = _read_upload(current, "current")
    if reference is not None:
        reference_img = _read_upload(reference, "reference")
        source = "uploaded"
    else:
        reference_img = cv2.imread(str(DEFAULT_REFERENCE), cv2.IMREAD_COLOR)
        if reference_img is None:
            raise HTTPException(503, "Reference image is unavailable. Upload a full-shelf reference image.")
        reference_img = _normalize(reference_img)
        source = "built-in synthetic demo"
    selected_roi = None
    if roi:
        try:
            selected_roi = json.loads(roi)
            if not isinstance(selected_roi, list):
                raise ValueError("Expected a coordinate list.")
            vision.roi_bounds(reference_img.shape[1], reference_img.shape[0], selected_roi)
        except (ValueError, TypeError) as error:
            raise HTTPException(400, "Invalid shelf selection. Choose a rectangle inside the reference image.") from error
    return _analyze(current_img, reference_img, source, selected_roi, rows, cols)


@app.post("/demo")
def demo():
    reference_img = cv2.imread(str(DEFAULT_REFERENCE), cv2.IMREAD_COLOR)
    current_img = cv2.imread(str(DEMO_CURRENT), cv2.IMREAD_COLOR)
    if reference_img is None or current_img is None:
        raise HTTPException(503, "Demo images are unavailable. Run python make_samples.py to recreate them.")
    return _analyze(current_img, reference_img, "built-in synthetic demo")


@app.post("/demo/{example}")
def real_demo(example: str):
    examples = {"real-one": 1, "real-two": 2}
    if example not in examples:
        raise HTTPException(404, "Unknown example.")
    number = examples[example]
    folder = SAMPLES / "external" / "shelfchange3d"
    reference = cv2.imread(str(folder / f"demo{number}_t0.png"))
    current = cv2.imread(str(folder / f"demo{number}_t1.png"))
    if reference is None or current is None:
        raise HTTPException(503, "The example photos are unavailable.")
    return _analyze(current, reference, "ShelfChange3D development example; not held-out accuracy evidence")


@app.post("/approve/{order_id}")
def approve(order_id: str):
    approved = agent.approve(order_id)
    if approved is None:
        raise HTTPException(404, "This draft is unavailable or has already been approved.")
    return {
        "approved": True,
        "sent": False,
        "message": "Draft approved locally. No supplier was contacted and no order was sent.",
        "approved_at": approved["approved_at"],
    }


@app.get("/orders")
def orders():
    return {"orders": storage.recent_orders(), "sent": False}


@app.get("/metrics")
def metrics():
    return dict(COUNTERS)


@app.get("/", response_class=FileResponse)
def home():
    """Serve the interface; browser assets live in static/."""
    return FileResponse(ROOT / "templates" / "index.html")
