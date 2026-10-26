"""Transparent perception -> decision -> human approval workflow."""
from datetime import UTC, datetime
import uuid

from . import vision

# Thresholds are intentionally explicit so the evaluation report can disclose them.
PRESENT_MAX = 0.35
GAP_MIN = 0.60
ZOOM_GAP_FRACTION = 0.75
ZOOM_PRESENT_FRACTION = 0.25
MIN_ALIGNMENT_CONFIDENCE = 0.25

# Demo-only memory store. Replace with durable storage and authentication before use in a shop.
_ORDERS: dict[str, dict] = {}


def run(ref, cur, rows=3, cols=6, labels=None):
    trace: list[dict] = []
    results: dict[tuple[int, int], dict] = {}

    aligned, confidence = vision.align(ref, cur)
    trace.append({
        "step": 1,
        "event": "shelf_alignment",
        "tool": "OpenCV 5 ORB + RANSAC homography",
        "observation": f"alignment confidence {confidence:.2f}",
    })
    if aligned is None or confidence < MIN_ALIGNMENT_CONFIDENCE:
        trace[-1]["decision"] = "request_recapture"
        return {
            "status": "recapture_requested",
            "message": "I could not align this image to the reference with enough confidence. Retake the photo with the whole shelf visible from a similar angle.",
            "confidence": confidence,
            "trace": trace,
            "results": results,
            "gaps": [],
            "uncertain": [],
            "aligned": None,
        }

    scores = vision.score_grid(ref, aligned, rows, cols)
    boxes = vision.grid_boxes(ref.shape[1], ref.shape[0], rows, cols)
    ambiguous = [cell for cell, score in scores.items() if PRESENT_MAX <= score <= GAP_MIN]
    trace.append({
        "step": 2,
        "event": "cell_scan",
        "tool": "OpenCV 5 normalized template comparison",
        "observation": f"{len(scores)} cells scored; {len(ambiguous)} need closer inspection",
        "decision": "reinspect_uncertain_cells" if ambiguous else "use_cell_scores",
    })

    for cell, score in scores.items():
        zoomed = cell in ambiguous
        zoom_score = None
        gap_fraction = None
        if zoomed:
            zoom_score, gap_fraction = vision.zoom_rescore(ref, aligned, boxes[cell])
            if gap_fraction >= ZOOM_GAP_FRACTION:
                status = "gap"
            elif gap_fraction <= ZOOM_PRESENT_FRACTION:
                status = "present"
            else:
                status = "uncertain"
            trace.append({
                "step": 3,
                "event": "active_reinspection",
                "tool": "OpenCV 5 finer 2x2 cell scan",
                "observation": f"cell {cell} score {score:.2f}; {gap_fraction:.0%} of subcells differ",
                "decision": status,
            })
        else:
            status = "gap" if score > GAP_MIN else "present"
        results[cell] = {
            "score": round(float(score), 4),
            "zoom_score": round(float(zoom_score), 4) if zoom_score is not None else None,
            "gap_fraction": round(float(gap_fraction), 4) if gap_fraction is not None else None,
            "status": status,
            "zoomed": zoomed,
        }

    gaps = [cell for cell, result in results.items() if result["status"] == "gap"]
    uncertain = [cell for cell, result in results.items() if result["status"] == "uncertain"]

    if gaps:
        names = [(labels or {}).get(cell, f"row {cell[0] + 1}, slot {cell[1] + 1}") for cell in gaps]
        order_id = uuid.uuid4().hex
        draft = "Restock draft (not sent):\n" + "\n".join(f"- {name}" for name in names)
        if uncertain:
            pending = ", ".join(f"row {r + 1}, slot {c + 1}" for r, c in uncertain)
            draft += f"\n\nReview before ordering: {pending}"
        _ORDERS[order_id] = {
            "draft": draft,
            "approved": False,
            "created_at": datetime.now(UTC).isoformat(),
        }
        status = "awaiting_approval"
        message = draft
        trace.append({
            "step": 4,
            "event": "human_approval_gate",
            "observation": f"{len(gaps)} likely gaps; {len(uncertain)} uncertain cells",
            "decision": "prepare_local_draft_and_wait_for_human",
        })
    elif uncertain:
        order_id = None
        status = "needs_review"
        message = "Some cells remain uncertain after closer inspection. Review the highlighted cells or retake the photo; no restock draft was created."
        trace.append({
            "step": 4,
            "event": "human_review_gate",
            "observation": f"{len(uncertain)} uncertain cells; no confident gaps",
            "decision": "request_human_review",
        })
    else:
        order_id = None
        status = "shelf_ok"
        message = "No likely gaps found in the scanned shelf."
        trace.append({
            "step": 4,
            "event": "no_action",
            "observation": "all cells scored as present",
            "decision": "no_restock_draft",
        })

    return {
        "status": status,
        "message": message,
        "order_id": order_id,
        "confidence": confidence,
        "trace": trace,
        "results": results,
        "gaps": gaps,
        "uncertain": uncertain,
        "aligned": aligned,
    }


def approve(order_id: str):
    """Record human approval in this demo; no supplier order is transmitted."""
    order = _ORDERS.get(order_id)
    if order is None or order["approved"]:
        return None
    order["approved"] = True
    order["approved_at"] = datetime.now(UTC).isoformat()
    return order
