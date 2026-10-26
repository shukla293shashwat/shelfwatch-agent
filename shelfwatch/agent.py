"""Perception, targeted reinspection, and a durable human approval gate."""
import uuid
from collections import defaultdict

from . import storage, vision

PRESENT_MAX = 0.35
GAP_MIN = 0.60
MIN_ALIGNMENT_CONFIDENCE = 0.25


def run(ref, cur, rows=3, cols=6, labels=None, roi=None, persist=True):
    bounds = vision.roi_bounds(ref.shape[1], ref.shape[0], roi)
    aligned, confidence, valid = vision.align_detailed(ref, cur)
    trace = [{
        "step": 1, "event": "shelf_alignment",
        "tool": "OpenCV 5 ORB + RANSAC homography",
        "observation": f"inlier ratio {confidence:.2f}; selected shelf bounds {bounds}",
    }]
    base = {"confidence": confidence, "trace": trace, "results": {}, "gaps": [],
            "uncertain": [], "aligned": aligned, "regions": [], "roi": list(bounds),
            "rows": rows, "cols": cols, "order_id": None}
    if aligned is None or confidence < MIN_ALIGNMENT_CONFIDENCE:
        trace[0]["decision"] = "request_recapture"
        return {**base, "status": "recapture_requested", "aligned": None,
                "message": "The photos could not be aligned reliably. Retake the photo from a similar angle with the whole selected shelf visible."}

    x0, y0, x1, y1 = bounds
    if float((valid[y0:y1, x0:x1] > 0).mean()) < 0.90:
        trace[0]["decision"] = "request_recapture"
        return {**base, "status": "recapture_requested", "aligned": None,
                "message": "Part of the selected shelf is outside the current photo. Retake it with the entire selected area visible."}

    boxes = vision.grid_boxes_in_roi(bounds, rows, cols)
    scores = vision.score_boxes(ref, aligned, boxes)
    regions = vision.find_changes(ref, aligned, valid, bounds)
    trace.append({"step": 2, "event": "localized_change_scan",
                  "tool": "OpenCV 5 Lab difference, local texture mask, morphology and connected components",
                  "observation": f"{len(regions)} local change regions inside the selected shelf; {rows * cols} reporting cells",
                  "decision": "reinspect_local_regions" if regions else "no_local_change"})

    by_cell = defaultdict(list)
    for region in regions:
        left, top, right, bottom = region["box"]
        col = min(cols - 1, int(((left + right) / 2 - x0) / (x1 - x0) * cols))
        row = min(rows - 1, int(((top + bottom) / 2 - y0) / (y1 - y0) * rows))
        region["cell"] = [row, col]
        by_cell[(row, col)].append(region)

    results = {}
    for cell, score in scores.items():
        local = by_cell[cell]
        zoom_score = gap_fraction = None
        status = "present"
        if local:
            zoom_score, gap_fraction = vision.zoom_rescore(ref, aligned, boxes[cell])
            removal_evidence = any(region["texture_loss"] >= vision.MIN_TEXTURE_LOSS for region in local)
            ambiguous_grid = PRESENT_MAX <= score <= GAP_MIN and 0.25 < gap_fraction < 0.75
            status = "gap" if removal_evidence and not ambiguous_grid else "uncertain"
            for region in local:
                region["status"] = status
            trace.append({"step": 3, "event": "active_reinspection",
                          "tool": "OpenCV 5 local edge/texture comparison + finer 2x2 inspection",
                          "observation": f"cell {cell}: {len(local)} regions; texture loss up to {max(r['texture_loss'] for r in local):.2f}; {gap_fraction:.0%} differing subcells",
                          "decision": status})
        results[cell] = {"score": round(float(score), 4),
                         "zoom_score": round(float(zoom_score), 4) if local else None,
                         "gap_fraction": round(float(gap_fraction), 4) if local else None,
                         "status": status, "zoomed": bool(local), "region_count": len(local)}

    gaps = [cell for cell, item in results.items() if item["status"] == "gap"]
    uncertain = [cell for cell, item in results.items() if item["status"] == "uncertain"]
    order_id = None
    if gaps:
        names = [(labels or {}).get(cell, f"row {cell[0] + 1}, slot {cell[1] + 1}") for cell in gaps]
        message = "Restock draft — verify the highlighted locations:\n" + "\n".join(f"- {name}" for name in names)
        message += "\n\nThese are affected cells, not product quantities. No order has been sent."
        if uncertain:
            message += "\nReview uncertain cells before ordering: " + ", ".join(f"row {r + 1}, slot {c + 1}" for r, c in uncertain)
        if persist:
            order_id = uuid.uuid4().hex
            storage.save_order(order_id, message)
        status, decision = "awaiting_approval", "prepare_draft_and_wait_for_human"
        event = "human_approval_gate"
    elif uncertain:
        message = "Appearance changed, but removal evidence is uncertain. Review the amber regions or retake the photo."
        status, decision, event = "needs_review", "request_human_review", "human_review_gate"
    else:
        message = "No likely gaps found inside the selected shelf area. Review the image before relying on this result."
        status, decision, event = "shelf_ok", "no_restock_draft", "no_action"
    trace.append({"step": 4, "event": event,
                  "observation": f"{len(gaps)} affected cells; {len(uncertain)} uncertain cells",
                  "decision": decision})
    return {**base, "status": status, "message": message, "order_id": order_id,
            "results": results, "gaps": gaps, "uncertain": uncertain, "regions": regions}


def approve(order_id):
    return storage.approve(order_id)
