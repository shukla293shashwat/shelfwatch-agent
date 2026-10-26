# External shelf-photo test — 26 October 2026

## Outcome

The upload/API path processed all three checks successfully, but the current detector failed to locate the removed products in both external photo pairs. The exact-image unchanged control passed. These failures show why the earlier synthetic fixture scores cannot establish practical reliability.

## Inputs and provenance

The original, unedited reference/current PNG pairs were downloaded from the [ShelfChange3D project website](https://zerone0011.github.io/ShelfChange3D/), by Lingyi Zhou and colleagues. Its robot demonstrations describe two products removed in demo 1 and one product removed in demo 2. This is a controlled research demonstration, not footage from our own shop or an independent retail benchmark.

- Demo 1: [reference](https://zerone0011.github.io/ShelfChange3D/static/images/demo1_t0.png), [current](https://zerone0011.github.io/ShelfChange3D/static/images/demo1_t1.png).
- Demo 2: [reference](https://zerone0011.github.io/ShelfChange3D/static/images/demo2_t0.png), [current](https://zerone0011.github.io/ShelfChange3D/static/images/demo2_t1.png).
- Control: demo 1 reference submitted as both reference and current.

All images are 640×400. They were uploaded to the running FastAPI `/analyze` route with the correct reference. No image edits, cropping or detector threshold changes were applied. Nothing was approved or sent.

## Observations

| Check | Expected scene change | Observed output | Assessment |
|---|---|---|---|
| Demo 1 | Two front cans removed near the middle of the upper shelf | `shelf_ok`, no gaps, no uncertain cells | Missed removal |
| Demo 2 | One yellow can removed near the middle of the upper shelf | `awaiting_approval`, gap at row 1 / column 6; actual removal near row 2 / column 4 classified present | Missed removal and false background alert |
| Unchanged control | No change | `shelf_ok`, no gaps, no uncertain cells | Passed control |

Rows and columns in this table are one-based. Removed-product centers in both pairs fall in approximately row 2 / column 4 of the fixed 3×6 grid, although their footprints can cross cell boundaries. Those locations were checked visually; they are not publisher-provided annotations. Multiple products can occupy the same grid cell, so a gap-cell count is not a removed-product count.

All three requests returned HTTP 200 and an ORB/RANSAC inlier ratio rounded to 1.000. This alignment statistic is not a probability that the gap detection is correct. Demo 2's actual changed cell scored only 0.1362 and was classified present, while background cell row 1 / column 6 scored 0.3582 and was escalated by the finer scan to a gap.

## Interpretation

The fixed full-image grid includes floor, robot hands and background. Small removed products occupy only part of a cell, diluting the template difference. Low-texture background can also cause unreliable normalized correlation. These observations suggest inspecting calibrated shelf/product regions and accounting for local image validity and texture before scoring. This is a diagnosis to investigate, not a measured fix.

No external precision/recall/F1 is reported: two positive pairs and an exact-image control, with approximate manual region labels, are insufficient for a benchmark. No general retail accuracy is claimed.

## Reproduce

With the four source images saved in `samples/external/shelfchange3d/` and the app running on port 8000:

```powershell
.\.venv\Scripts\python.exe test_external_photos.py
```

Machine-readable evidence, image SHA-256 hashes, timing, all cell scores, decision traces and annotated overlays are written to `reports/external-photos/`. The shareable folder includes the source pairs with credits in `THIRD_PARTY_NOTICES.md`, plus saved evidence under `docs/evidence/external-photos/`. Fresh generated reports stay out of version control. The external check exits with a failure status while the removal cases fail.

