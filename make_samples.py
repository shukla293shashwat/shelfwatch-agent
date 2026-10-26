"""Generate clearly synthetic fixtures for reproducible smoke evaluation."""
from pathlib import Path
import csv

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
EVAL = SAMPLES / "eval"
SAMPLES.mkdir(exist_ok=True)
EVAL.mkdir(exist_ok=True)

WIDTH, HEIGHT, ROWS, COLS = 900, 450, 3, 6
rng = np.random.default_rng(1)
reference = np.full((HEIGHT, WIDTH, 3), 200, dtype=np.uint8)
cell_w, cell_h = WIDTH // COLS, HEIGHT // ROWS

# This illustration is intentionally synthetic; it is not a real retail image.
for row in range(ROWS):
    for col in range(COLS):
        x0, y0 = col * cell_w + 12, row * cell_h + 12
        product_color = tuple(int(value) for value in rng.integers(30, 230, 3))
        cv2.rectangle(reference, (x0, y0), (x0 + cell_w - 24, y0 + cell_h - 24), product_color, -1)
        for _ in range(25):
            point = (
                int(rng.integers(x0, x0 + cell_w - 24)),
                int(rng.integers(y0, y0 + cell_h - 24)),
            )
            dot_color = tuple(int(value) for value in rng.integers(0, 255, 3))
            cv2.circle(reference, point, int(rng.integers(3, 10)), dot_color, -1)
        cv2.putText(
            reference,
            f"P{row}{col}",
            (x0 + 8, y0 + 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (255, 255, 255),
            2,
        )

# Remove three complete products, then partially obscure a fourth. The partial
# occlusion should trigger a targeted 2x2 reinspection and remain uncertain.
current = reference.copy()
known_gaps = [(0, 2), (1, 4), (2, 0)]
for row, col in known_gaps:
    current[row * cell_h:(row + 1) * cell_h, col * cell_w:(col + 1) * cell_w] = 200

review_cell = (1, 2)
row, col = review_cell
x0, y0, x1, y1 = col * cell_w, row * cell_h, (col + 1) * cell_w, (row + 1) * cell_h
cv2.rectangle(current, (x0, y0), (x0 + (x1 - x0) // 2, y1), (200, 200, 200), -1)

# Slight perspective and brightness changes emulate a re-taken phone photo.
perspective = cv2.getPerspectiveTransform(
    np.float32([[0, 0], [WIDTH, 0], [WIDTH, HEIGHT], [0, HEIGHT]]),
    np.float32([[15, 10], [WIDTH - 20, 5], [WIDTH - 5, HEIGHT - 15], [10, HEIGHT - 10]]),
)
current = cv2.warpPerspective(current, perspective, (WIDTH, HEIGHT), borderValue=(200, 200, 200))
current = cv2.convertScaleAbs(current, alpha=0.85, beta=-10)

flat = np.full_like(reference, 200)
cv2.imwrite(str(SAMPLES / "reference.jpg"), reference)
cv2.imwrite(str(SAMPLES / "current_3_missing.jpg"), current)
cv2.imwrite(str(SAMPLES / "current_unaligned.jpg"), flat)

# Evaluation inputs are separate copies so real photos can be added without
# changing the built-in demo fixture.
cv2.imwrite(str(EVAL / "synthetic_partial_stock.jpg"), current)
cv2.imwrite(str(EVAL / "synthetic_full_stock.jpg"), reference)
cv2.imwrite(str(EVAL / "synthetic_unaligned.jpg"), flat)

with (EVAL / "labels.csv").open("w", newline="", encoding="utf-8") as handle:
    writer = csv.DictWriter(handle, fieldnames=["image", "gap_cells", "review_cells", "expected_status"])
    writer.writeheader()
    writer.writerow({
        "image": "synthetic_partial_stock.jpg",
        "gap_cells": ";".join(f"{r}-{c}" for r, c in known_gaps),
        "review_cells": f"{review_cell[0]}-{review_cell[1]}",
        "expected_status": "awaiting_approval",
    })
    writer.writerow({
        "image": "synthetic_full_stock.jpg",
        "gap_cells": "",
        "review_cells": "",
        "expected_status": "shelf_ok",
    })
    writer.writerow({
        "image": "synthetic_unaligned.jpg",
        "gap_cells": "",
        "review_cells": "",
        "expected_status": "recapture_requested",
    })

print(f"Wrote synthetic demo and evaluation fixtures to {SAMPLES}")
print("Expected missing cells:", known_gaps)
print("Expected human-review cell:", review_cell)
