# Five-minute demo recording plan

Aim for about **4 minutes 40 seconds**, leaving a buffer below the five-minute limit. Record the real application and your own voice. Add your presenter introduction yourself if the hackathon requires you to appear on camera. Do not present a locally running page as AWS deployment evidence.

## 0:00–0:20 — Introduce the problem

“My name is Shashwat Shukla. I built ShelfWatch to compare a shelf with a stocked reference, show candidate gaps, and let a person review a restock draft. My focus is an explainable perception-to-action workflow.”

## 0:20–1:15 — Run the generated example

Open the app and click **Try synthetic demo**. Show the current image, three candidate gap cells and one uncertain cell. Expand the trace and point out alignment, local change scanning, reinspection and the approval gate.

“These pictures are generated fixtures. They make the decision path reproducible; they are not proof of store accuracy. The agent takes another inspection step when it finds a local change, and can keep a location under review rather than treating every difference as an empty slot.”

## 1:15–1:55 — Show shelf selection and local regions

Upload a matched reference/current pair. Drag over the actual shelf area and show the numeric keyboard controls. Explain that the grid groups reporting locations while smaller regions drive detection. If using the supplied development photos, credit ShelfChange3D on screen and identify them as known development examples.

“The first version missed these small changes because it averaged over a large cell. The updated version uses local color differences and texture evidence to find the affected region. A region or cell is not a product count.”

## 1:55–2:25 — Show approval and saved state

Review the draft, approve it, then show that approval is recorded in SQLite. Do not claim an order was sent.

“Approval is a local audit event. Repeated approval is rejected, and photos are not stored. This prototype has no supplier API.”

## 2:25–3:10 — Explain the architecture

Show `docs/architecture.svg` and briefly open `shelfwatch/vision.py` and `shelfwatch/agent.py`.

“OpenCV 5 handles ORB feature matching, homography alignment, the validity mask, Lab differences, morphology, connected components, and finer reinspection. The agent uses that evidence to request a retake, prepare a draft, or ask for review.”

## 3:10–3:55 — Show results and a failure

Show `docs/evidence/v2-synthetic-stress.json` and the failing `samples/validation/137_partial_occlusion.jpg` example. State the dataset type before the numbers.

“On a separate generated stress set, 32 of 33 expected outcomes passed. Gap-cell precision was 94.7%, recall 100%, and F1 97.3%. One partially covered item was wrongly marked as a candidate gap. These generated results do not establish retail accuracy. The extra public previews also contain annotation boxes, so I report them separately rather than calling them a raw-photo benchmark.”

## 3:55–4:30 — Show actual AWS evidence

**Only after AWS deployment succeeds:** open the live HTTPS URL, show `/health` reporting OpenCV 5, run one authenticated analysis, and show the stack/log group with sensitive values hidden. Mention that OpenCV analysis actually runs on EC2. Do not display passwords, tokens, access keys or customer images.

**If activation is still pending:** state that clearly. The deployment template is not a deployed service and does not satisfy the AWS requirement by itself. Do not record a success claim until the endpoint is verified.

## 4:30–4:40 — Close with the next validation step

“The next test is a larger labelled set of raw shelf photos from varied shops, with development and test examples kept separate. The current workflow remains supervised because appearance changes alone cannot reliably distinguish every removal, rearrangement or occlusion.”

## Before uploading the video

- Keep the full recording under five minutes.
- Confirm the required presenter/face segment is included.
- Hide the access code, AWS account details and private contact/billing information.
- Keep generated, development and additional diagnostic results clearly labelled.
- Verify the public video link works when signed out.
- Use the actual verified live URL in the submission; do not substitute localhost.
