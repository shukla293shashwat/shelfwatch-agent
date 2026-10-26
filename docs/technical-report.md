# ShelfWatch technical report — version 2

**Author:** Shashwat Shukla  
**Runtime checked:** Python 3.12, OpenCV 5.0.0 (package 5.0.0.93)  
**Status:** local prototype with development regression checks and separate diagnostic datasets. AWS delivery is prepared but not yet verified live.

## Problem

ShelfWatch explores a human-supervised way to check a shelf against a stocked reference and prepare a replenishment suggestion. A useful result must show where the suspected gap is and how the agent reached that decision. It must also request another photo or human review when the evidence is insufficient.

## Method

The user selects a shelf rectangle in a reference photo. The selection is normalized, with numeric keyboard controls as an alternative to dragging. OpenCV ORB descriptors and RANSAC homography align the current photo; a validity mask checks that at least 90% of the selected shelf is covered. An unreliable alignment or incomplete selected-area coverage requests a retake.

Inside the selected area, a median Lab-color offset reduces uniform illumination differences. A local reference-texture mask suppresses smooth background. Pixel differences, opening/closing morphology and connected components propose small changed regions. This avoids averaging a missing can into a large reporting cell. Local edge/texture loss and 2×2 reinspection then inform a gap/review decision. The reporting grid groups affected locations; it is not an object detector or product counter.

Detected locations produce a draft and a human approval gate. SQLite records the draft, creation time, approval time and audit events. Approval is atomic and repeat approval is rejected. No supplier integration exists and no order is transmitted.

## Development history and separation

Version 1 passed its generated fixture checks but failed the two ShelfChange3D demonstration pairs: it missed removed products and produced one background alert. Those images were then used for development and must not be presented as untouched test data. Version 2 finds two localized regions in the correct cell in demo 1 and one in demo 2, with no background gap. The unchanged-image control passes.

An initial detector freeze records parameters and source hashes in `docs/evidence/detector-freeze.json`. The detector's decision thresholds were not tuned to fix the subsequent 33-case stress-set failure. Evaluation reports also record the exact source and input hashes used. Source serialization and operational code changes are separate from decision-threshold selection.

## Evaluation

| Evidence group | Result | Interpretation |
| --- | --- | --- |
| Generated demo fixtures | 3/3 expected outcomes; gap TP=3, FP=0, FN=0 | Reproducible smoke checks only |
| Two real-photo development pairs plus unchanged control | Correct affected location in both positive cases; unchanged control passes | Regression evidence on known examples |
| Separate generated stress suite | 32/33 expected outcomes; gap TP=18, FP=1, FN=0 | Cell precision 94.7%, recall 100%, F1 97.3% on generated images |
| Three additional annotated previews plus unchanged controls | 6/6 coarse diagnostic checks; four grouped changed areas matched at IoU ≥0.25; an extra uncertain region in one pair | Visible annotation boxes and approximate manual grouped-area labels prevent an uncontaminated raw-photo accuracy claim |

The generated stress suite uses three seeds unused by the demonstration and includes missing items, partial occlusion, a uniform brightness shift, slight viewpoint change, blank/unrelated images, incomplete view coverage and a change outside the selected area. Mean local analysis time in the recorded run was about 0.225 seconds per stress image, excluding upload and deployment latency. This is a local machine observation, not AWS performance.

### Retained failure

For `137_partial_occlusion.jpg`, a partly covered product was marked as a candidate gap rather than uncertain. The item was not actually removed. This false alert remains in the report. An occluder can remove texture in the same way as an absent product, so appearance comparison alone cannot guarantee the meaning of a change. Human review reduces the chance of acting on the error, but does not improve the measured detection accuracy.

### Reproduce

```powershell
python test_pipeline.py
python evaluate.py
python evaluate.py --labels samples/validation/labels.csv --kind synthetic_stress --output reports/stress.json
python evaluate.py --labels samples/holdout/labels.csv --kind annotated_preview --output reports/previews.json
python -m unittest discover -s tests -v
```

Run these within the pinned Python environment. The stress command exits with a failure status while the occlusion case fails and still writes its evidence. Original third-party photo credits and reuse notes are in `THIRD_PARTY_NOTICES.md`.

## Delivery and responsible operation

The FastAPI service provides the interface, uploads, generated and real-photo development examples, annotated outputs, an agent trace and local approval. Shared access-code authentication protects analysis, approvals, history and metrics when configured. Public mode fails startup without a sufficiently long code. Request/image sizes, concurrent analysis and requests per client are bounded. Logs contain request IDs, paths, status and timing without images or access codes. Photos are processed in memory; draft and audit records contain no photos.

The AWS deployment code targets EC2 for the actual OpenCV/FastAPI runtime, with an encrypted private S3 source archive, scoped IAM permissions, an SSM SecureString for the demo code, HTTPS through Caddy, CloudWatch logs and a SQLite volume. A source SHA-256 check precedes installation. The driver refuses to create resources unless an active AWS Free plan and sufficient remaining credit are verified. The demo is disposable and has an explicit lifetime and cleanup procedure.

The AWS account recently completed user-side verification. The last service probe still returned Free-plan state `NOT_STARTED` and EC2 `OptInRequired`; no project resources or live endpoint have been created. This is an external activation dependency. Do not describe the templates or a successful console login as a completed AWS deployment. After activation, record the actual region, stack status, image digests, HTTPS health response, authorized analysis and logs before submission.

## Limits and remaining validation

- No SKU identity, product quantity, stock database or supplier API.
- Changed appearance does not prove removal; occlusion, rearrangement and packaging changes can confuse the rules.
- The pixel-change threshold, reference-texture mask and texture-loss gate need evaluation on varied raw store photos.
- Localized regions can merge adjacent products; labels and metrics must reflect regions or cells rather than fabricated product counts.
- The shared demo code is not a multi-user identity system. SQLite and in-memory rate limits assume a single demo instance.
- A SQLite volume survives a container restart, but is not a backup and is deleted when the disposable AWS instance/storage is removed.
- A larger raw-photo held-out store set, verified AWS delivery, and the final presenter-led video remain necessary before claiming a complete hackathon submission.
