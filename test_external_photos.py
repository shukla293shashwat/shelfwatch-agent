"""Check public shelf-photo pairs through a running ShelfWatch API.

These are diagnostic examples, not a representative retail benchmark.
The image pairs and original source are listed in THIRD_PARTY_NOTICES.md.
"""
import argparse
import base64
import hashlib
import html
import json
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
IMAGES = ROOT / "samples" / "external" / "shelfchange3d"
OUTPUT = ROOT / "reports" / "external-photos"
SOURCE = "https://zerone0011.github.io/ShelfChange3D/"

# Labels describe removed-product centers, not exact change segmentation.
# Coordinates are zero-based; both demos change the middle of the upper shelf.
CASES = [
    ("demo1_two_removed", "demo1_t0.png", "demo1_t1.png", 2, {(1, 3)}),
    ("demo2_one_removed", "demo2_t0.png", "demo2_t1.png", 1, {(1, 3)}),
    ("unchanged_control", "demo1_t0.png", "demo1_t0.png", 0, set()),
]


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def upload_pair(base_url, reference_name, current_name):
    """Send the same two fields as the browser's upload form."""
    boundary = "ShelfWatch" + uuid.uuid4().hex
    body = bytearray()

    for field, name in [("reference", reference_name), ("current", current_name)]:
        body.extend(
            f'--{boundary}\r\n'
            f'Content-Disposition: form-data; name="{field}"; filename="{name}"\r\n'
            'Content-Type: image/png\r\n\r\n'.encode()
        )
        body.extend((IMAGES / name).read_bytes())
        body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        base_url.rstrip("/") + "/analyze",
        data=bytes(body),
        headers={"Content-Type": "multipart/form-data; boundary=" + boundary},
        method="POST",
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.load(response)
        status = response.status
    return status, round(time.perf_counter() - started, 3), result


def assess_case(base_url, case):
    name, reference, current, removed_count, expected_cells = case
    status, seconds, result = upload_pair(base_url, reference, current)
    overlay = result.pop("overlay", None)
    if overlay:
        (OUTPUT / f"{name}_overlay.jpg").write_bytes(base64.b64decode(overlay))

    gaps = {tuple(cell) for cell in result.get("gaps", [])}
    uncertain = {tuple(cell) for cell in result.get("uncertain", [])}
    if removed_count:
        passed = status == 200 and gaps == expected_cells
    else:
        passed = status == 200 and result.get("status") == "shelf_ok"

    return {
        "case": name,
        "reference": reference,
        "current": current,
        "reference_sha256": file_hash(IMAGES / reference),
        "current_sha256": file_hash(IMAGES / current),
        "source_reported_products_removed": removed_count,
        "http_status": status,
        "elapsed_seconds": seconds,
        "manual_primary_changed_cells_zero_based": sorted(map(list, expected_cells)),
        "localization_check_pass": passed,
        "reviewed_expected_location": bool(uncertain & expected_cells),
        "unexpected_gap_cells": sorted(map(list, gaps - expected_cells)),
        "result": result,
    }


def image_figure(label, path):
    if not path.exists():
        return ""
    image_type = "png" if path.suffix == ".png" else "jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return (
        f'<figure><img src="data:image/{image_type};base64,{encoded}" '
        f'alt="{html.escape(label)}"><figcaption>{html.escape(label)}</figcaption></figure>'
    )


def save_visual_report(cases):
    """Embed photos so the report also opens directly from a shared folder."""
    cards = []
    for case in cases:
        result = case["result"]
        outcome = "PASS" if case["localization_check_pass"] else "FAIL"
        title = html.escape(case["case"].replace("_", " "))
        figures = [
            image_figure("Reference", IMAGES / case["reference"]),
            image_figure("Current photo", IMAGES / case["current"]),
            image_figure("ShelfWatch output", OUTPUT / (case["case"] + "_overlay.jpg")),
        ]
        cards.append(
            f'<article><h2>{title} <span>{outcome}</span></h2>'
            f'<p>Source-reported removals: {case["source_reported_products_removed"]}. '
            f'API status: {html.escape(result["status"])}. '
            f'Gap cells (zero-based): {html.escape(str(result["gaps"]))}.</p>'
            f'<div class="images">{"".join(figures)}</div></article>'
        )

    passed = sum(case["localization_check_pass"] for case in cases)
    template = (ROOT / "templates" / "external_report.html").read_text(encoding="utf-8")
    page = template.replace("{{summary}}", f"{passed} of {len(cases)} diagnostic checks passed.")
    page = page.replace("{{cases}}", "\n".join(cards))
    (OUTPUT / "index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    OUTPUT.mkdir(parents=True, exist_ok=True)

    for _, reference, current, _, _ in CASES:
        for name in (reference, current):
            if not (IMAGES / name).is_file():
                raise SystemExit(f"Missing sample: {IMAGES / name}. See THIRD_PARTY_NOTICES.md.")

    try:
        cases = [assess_case(args.base_url, case) for case in CASES]
    except urllib.error.URLError as error:
        raise SystemExit(f"Could not complete the upload to {args.base_url}. Start the app first. {error}")

    report = {
        "source": SOURCE,
        "retrieved_date": "2026-10-26",
        "tested_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "method": "Unmodified research demo pairs uploaded via POST /analyze, followed by an exact-image control.",
        "limits": "Two positive pairs and one exact-image control. Approximate, manually inspected product-center cells are not publisher-provided cell labels. Grid cells are not product counts. No precision/recall/F1 or general accuracy is inferred. No approval requested.",
        "cases": cases,
    }
    (OUTPUT / "results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    save_visual_report(cases)

    for case in cases:
        outcome = "PASS" if case["localization_check_pass"] else "FAIL"
        result = case["result"]
        print(f"{outcome} {case['case']}: {result['status']}; gaps={result['gaps']}")
    print("Results:", OUTPUT / "results.json")
    print("Visual report:", OUTPUT / "index.html")
    return 0 if all(case["localization_check_pass"] for case in cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
