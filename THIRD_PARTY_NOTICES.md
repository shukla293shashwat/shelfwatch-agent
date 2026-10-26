# Third-party photo credits

The four original PNG images in `samples/external/shelfchange3d/` were downloaded on 26 October 2026 from the ShelfChange3D project by Lingyi Zhou, Yunke Wang, Mengyu Zheng, Wenbo Wang, Zijian Wang and Chang Xu.

Project: https://zerone0011.github.io/ShelfChange3D/
Paper: https://arxiv.org/abs/2610.01283

Original files:

- https://zerone0011.github.io/ShelfChange3D/static/images/demo1_t0.png
- https://zerone0011.github.io/ShelfChange3D/static/images/demo1_t1.png
- https://zerone0011.github.io/ShelfChange3D/static/images/demo2_t0.png
- https://zerone0011.github.io/ShelfChange3D/static/images/demo2_t1.png

The project page describes demo 1 as two products removed and demo 2 as one product removed. ShelfWatch uses these pairs for a small external diagnostic; no ownership of the photographs or endorsement by their authors is claimed. The annotated overlays and saved visual report under `docs/evidence/external-photos/` contain these source images.

No explicit redistribution license was recorded for those photos. They remain third-party material; consult the original authors' terms before republishing them. The generated fixtures in `samples/reference.jpg`, `samples/current_3_missing.jpg`, `samples/current_unaligned.jpg` and `samples/eval/` are created locally by `make_samples.py` and are separate from these external images.

OpenCV, NumPy, FastAPI, Uvicorn and the other dependencies retain their respective licenses. Exact installed package versions are listed in `requirements.lock`.

## Additional publisher previews

The six JPG images in `samples/holdout/` were retrieved from the same ShelfChange3D website after the initial detector settings were recorded:

- `static/images/bench/real1_t0.jpg` and `real1_t1.jpg`
- `static/images/bench/real2_t0.jpg` and `real2_t1.jpg`
- `static/images/bench/real3_t0.jpg` and `real3_t1.jpg`

Their base URL is `https://zerone0011.github.io/ShelfChange3D/`. They contain visible annotation boxes and are used only as a separately labelled diagnostic. The `holdout` directory name denotes when they were first inspected; it does not make annotated website previews an uncontaminated benchmark. Manual grouped-region labels in `labels.csv` are local diagnostic annotations, not the original dataset ground truth. The same third-party ownership and unconfirmed-redistribution-license notice above applies to these files.
