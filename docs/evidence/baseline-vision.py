"""OpenCV 5 shelf alignment, cell scoring, active reinspection, and overlays."""
import cv2
import numpy as np


def _check_image(img, name="image"):
    if not isinstance(img, np.ndarray) or img.size == 0:
        raise ValueError(f"{name} is empty or is not an image array")
    if img.ndim != 3 or img.shape[2] != 3:
        raise ValueError(f"{name} must be a 3-channel BGR image")
    if min(img.shape[:2]) < 120:
        raise ValueError(f"{name} is too small; use an image at least 120 pixels on each side")


def _prep(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    enhanced = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return cv2.GaussianBlur(enhanced, (5, 5), 0)


def align(ref, cur, nfeat=4000):
    """Warp the current photo into reference coordinates using ORB + RANSAC.

    Returns (aligned_image_or_none, inlier_ratio). A low overlap or invalid
    transform is rejected rather than allowing unreliable cell scores.
    """
    _check_image(ref, "reference image")
    _check_image(cur, "current image")
    orb = cv2.ORB_create(nfeatures=nfeat, scaleFactor=1.2, nlevels=8, fastThreshold=12)
    k_ref, d_ref = orb.detectAndCompute(_prep(ref), None)
    k_cur, d_cur = orb.detectAndCompute(_prep(cur), None)
    if d_ref is None or d_cur is None or len(k_ref) < 10 or len(k_cur) < 10:
        return None, 0.0

    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d_cur, d_ref)
    matches = sorted(matches, key=lambda match: match.distance)[:500]
    if len(matches) < 10:
        return None, 0.0

    src = np.float32([k_cur[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([k_ref[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    transform, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if transform is None or mask is None or not np.isfinite(transform).all():
        return None, 0.0

    inliers = int(mask.sum())
    confidence = inliers / len(matches)
    if inliers < 8:
        return None, confidence

    ref_h, ref_w = ref.shape[:2]
    cur_h, cur_w = cur.shape[:2]
    corners = np.float32([[[0, 0], [cur_w - 1, 0], [cur_w - 1, cur_h - 1], [0, cur_h - 1]]])
    projected = cv2.perspectiveTransform(corners, transform)
    if not np.isfinite(projected).all():
        return None, confidence
    projected_area = abs(cv2.contourArea(projected[0]))
    reference_area = float(ref_w * ref_h)
    area_ratio = projected_area / max(reference_area, 1.0)
    if not 0.35 <= area_ratio <= 2.8:
        return None, confidence

    aligned = cv2.warpPerspective(cur, transform, (ref_w, ref_h), flags=cv2.INTER_LINEAR)
    source_mask = np.full((cur_h, cur_w), 255, dtype=np.uint8)
    valid_mask = cv2.warpPerspective(source_mask, transform, (ref_w, ref_h), flags=cv2.INTER_NEAREST)
    overlap = float(np.count_nonzero(valid_mask)) / reference_area
    if overlap < 0.55:
        return None, confidence * overlap
    return aligned, confidence


def cell_score(ref_g, cur_g, box):
    """Return 0 for a close match and 1 for a strong visual difference."""
    x0, y0, x1, y1 = box
    reference_cell = ref_g[y0:y1, x0:x1]
    current_cell = cur_g[y0:y1, x0:x1]
    if reference_cell.size == 0 or current_cell.size == 0:
        return 0.5

    # A blank reference cell means there is no expected product to detect.
    reference_texture = float(reference_cell.std())
    current_texture = float(current_cell.std())
    flat_limit = 4.0
    if reference_texture < flat_limit and current_texture < flat_limit:
        return 0.0
    if reference_texture < flat_limit:
        return 0.0
    if current_texture < flat_limit:
        return 1.0

    correlation = float(cv2.matchTemplate(current_cell, reference_cell, cv2.TM_CCOEFF_NORMED)[0, 0])
    if not np.isfinite(correlation):
        return 0.5
    return float(np.clip(1.0 - max(correlation, 0.0), 0.0, 1.0))


def grid_boxes(width, height, rows, cols):
    if rows < 1 or cols < 1:
        raise ValueError("rows and columns must be positive")
    xs = np.linspace(0, width, cols + 1).astype(int)
    ys = np.linspace(0, height, rows + 1).astype(int)
    return {
        (row, col): (xs[col], ys[row], xs[col + 1], ys[row + 1])
        for row in range(rows)
        for col in range(cols)
    }


def score_grid(ref, aligned, rows, cols):
    _check_image(ref, "reference image")
    _check_image(aligned, "aligned image")
    if ref.shape[:2] != aligned.shape[:2]:
        raise ValueError("aligned image must match reference dimensions")
    ref_gray, cur_gray = _prep(ref), _prep(aligned)
    height, width = ref_gray.shape
    return {
        cell: cell_score(ref_gray, cur_gray, box)
        for cell, box in grid_boxes(width, height, rows, cols).items()
    }


def zoom_rescore(ref, aligned, box, sub=2):
    """Re-score an ambiguous cell with a finer sub-grid.

    The returned fraction is the share of subcells with strong visual change;
    this evidence can change the agent's next decision.
    """
    if sub < 2:
        raise ValueError("sub-grid must have at least two divisions")
    ref_gray, cur_gray = _prep(ref), _prep(aligned)
    x0, y0, x1, y1 = box
    sub_boxes = grid_boxes(x1 - x0, y1 - y0, sub, sub)
    scores = [
        cell_score(ref_gray, cur_gray, (x0 + sx0, y0 + sy0, x0 + sx1, y0 + sy1))
        for sx0, sy0, sx1, sy1 in sub_boxes.values()
    ]
    return float(np.mean(scores)), float(np.mean(np.asarray(scores) > 0.5))


def overlay(aligned, results, rows, cols):
    out = aligned.copy()
    height, width = out.shape[:2]
    palette = {"gap": (38, 58, 220), "present": (34, 148, 92), "uncertain": (0, 165, 230)}
    labels = {"gap": "GAP", "present": "OK", "uncertain": "REVIEW"}
    for (row, col), (x0, y0, x1, y1) in grid_boxes(width, height, rows, cols).items():
        result = results.get((row, col), {})
        status = result.get("status", "uncertain")
        color = palette.get(status, palette["uncertain"])
        cv2.rectangle(out, (x0, y0), (x1 - 1, y1 - 1), color, 3)
        title = f"R{row + 1} C{col + 1}  {labels.get(status, '?')}"
        cv2.putText(out, title, (x0 + 7, y0 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2, cv2.LINE_AA)
    return out
