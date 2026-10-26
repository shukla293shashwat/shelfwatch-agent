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


def align_detailed(ref, cur, nfeat=4000):
    """Warp the current photo into reference coordinates using ORB + RANSAC.

    Returns (aligned_image_or_none, inlier_ratio, valid_pixel_mask). A low overlap or invalid
    transform is rejected rather than allowing unreliable cell scores.
    """
    _check_image(ref, "reference image")
    _check_image(cur, "current image")
    orb = cv2.ORB_create(nfeatures=nfeat, scaleFactor=1.2, nlevels=8, fastThreshold=12)
    k_ref, d_ref = orb.detectAndCompute(_prep(ref), None)
    k_cur, d_cur = orb.detectAndCompute(_prep(cur), None)
    if d_ref is None or d_cur is None or len(k_ref) < 10 or len(k_cur) < 10:
        return None, 0.0, None

    matches = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True).match(d_cur, d_ref)
    matches = sorted(matches, key=lambda match: match.distance)[:500]
    if len(matches) < 10:
        return None, 0.0, None

    src = np.float32([k_cur[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
    dst = np.float32([k_ref[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)
    transform, mask = cv2.findHomography(src, dst, cv2.RANSAC, 4.0)
    if transform is None or mask is None or not np.isfinite(transform).all():
        return None, 0.0, None

    inliers = int(mask.sum())
    confidence = inliers / len(matches)
    if inliers < 8:
        return None, confidence, None

    ref_h, ref_w = ref.shape[:2]
    cur_h, cur_w = cur.shape[:2]
    corners = np.float32([[[0, 0], [cur_w - 1, 0], [cur_w - 1, cur_h - 1], [0, cur_h - 1]]])
    projected = cv2.perspectiveTransform(corners, transform)
    if not np.isfinite(projected).all():
        return None, confidence, None
    projected_area = abs(cv2.contourArea(projected[0]))
    reference_area = float(ref_w * ref_h)
    area_ratio = projected_area / max(reference_area, 1.0)
    if not 0.35 <= area_ratio <= 2.8:
        return None, confidence, None

    aligned = cv2.warpPerspective(cur, transform, (ref_w, ref_h), flags=cv2.INTER_LINEAR)
    source_mask = np.full((cur_h, cur_w), 255, dtype=np.uint8)
    valid_mask = cv2.warpPerspective(source_mask, transform, (ref_w, ref_h), flags=cv2.INTER_NEAREST)
    overlap = float(np.count_nonzero(valid_mask)) / reference_area
    if overlap < 0.55:
        return None, confidence * overlap, None
    return aligned, confidence, valid_mask


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


def overlay(aligned, results, rows, cols, roi=None, regions=None):
    out = aligned.copy()
    height, width = out.shape[:2]
    palette = {"gap": (38, 58, 220), "present": (34, 148, 92), "uncertain": (0, 165, 230)}
    labels = {"gap": "GAP", "present": "OK", "uncertain": "REVIEW"}
    for (row, col), (x0, y0, x1, y1) in grid_boxes_in_roi(roi or (0, 0, width, height), rows, cols).items():
        result = results.get((row, col), {})
        status = result.get("status", "uncertain")
        color = palette.get(status, palette["uncertain"])
        cv2.rectangle(out, (x0, y0), (x1 - 1, y1 - 1), color, 3)
        title = f"R{row + 1} C{col + 1}  {labels.get(status, '?')}"
        cv2.putText(out, title, (x0 + 7, y0 + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.48, color, 2, cv2.LINE_AA)
    for region in regions or []:
        x0, y0, x1, y1 = region["box"]
        color = palette.get(region["status"], palette["uncertain"])
        cv2.rectangle(out, (x0, y0), (x1, y1), color, 3)
    return out


# Fixed before the separate evaluation run. Development pairs are not held out.
PIXEL_CHANGE_THRESHOLD = 22.0
MIN_LOCAL_STD = 5.0
MIN_TEXTURE_LOSS = 0.30
MIN_COMPONENT_FRACTION = 0.0008


def align(ref, cur, nfeat=4000):
    """Compatibility helper for callers that do not need the validity mask."""
    aligned, confidence, _ = align_detailed(ref, cur, nfeat)
    return aligned, confidence


def roi_bounds(width, height, roi=None):
    """Convert a normalized [left, top, right, bottom] selection to pixels."""
    if roi is None:
        return (0, 0, width, height)
    if len(roi) != 4 or not np.isfinite(roi).all():
        raise ValueError("Shelf area must contain four finite coordinates.")
    left, top, right, bottom = map(float, roi)
    if not (0 <= left < right <= 1 and 0 <= top < bottom <= 1):
        raise ValueError("Shelf area must stay within the image and have positive width and height.")
    bounds = (round(left * width), round(top * height), round(right * width), round(bottom * height))
    if bounds[2] - bounds[0] < 32 or bounds[3] - bounds[1] < 32:
        raise ValueError("Select a shelf area at least 32 pixels wide and tall.")
    return bounds


def grid_boxes_in_roi(bounds, rows, cols):
    left, top, right, bottom = bounds
    return {cell: (left + x0, top + y0, left + x1, top + y1)
            for cell, (x0, y0, x1, y1) in grid_boxes(right - left, bottom - top, rows, cols).items()}


def score_boxes(ref, aligned, boxes):
    reference_gray, current_gray = _prep(ref), _prep(aligned)
    return {cell: cell_score(reference_gray, current_gray, box) for cell, box in boxes.items()}


def find_changes(ref, aligned, valid_mask, bounds):
    """Propose small local changes instead of averaging them into a large cell.

    A robust global Lab offset reduces uniform illumination changes. A local
    reference-texture mask suppresses smooth background, then connected
    components localize changes. Texture loss is evidence of a possible removal,
    not a semantic guarantee: an occluder can produce similar evidence.
    """
    left, top, right, bottom = bounds
    reference = cv2.GaussianBlur(cv2.cvtColor(ref, cv2.COLOR_BGR2LAB), (5, 5), 0).astype(np.float32)
    current = cv2.GaussianBlur(cv2.cvtColor(aligned, cv2.COLOR_BGR2LAB), (5, 5), 0).astype(np.float32)
    valid = cv2.erode(valid_mask, np.ones((7, 7), np.uint8)) > 0
    allowed = np.zeros(ref.shape[:2], dtype=bool)
    allowed[top:bottom, left:right] = True
    allowed &= valid
    if not allowed.any():
        return []
    offset = np.median((current - reference)[allowed], axis=0)
    difference = np.max(np.abs((current - offset) - reference), axis=2)

    gray_ref = cv2.GaussianBlur(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    gray_cur = cv2.GaussianBlur(cv2.cvtColor(aligned, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    values = gray_ref.astype(np.float32)
    local_mean = cv2.blur(values, (9, 9))
    local_std = np.sqrt(np.maximum(0, cv2.blur(values * values, (9, 9)) - local_mean * local_mean))
    mask = ((difference > PIXEL_CHANGE_THRESHOLD) & (local_std > MIN_LOCAL_STD) & allowed).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
    mask[~allowed] = 0
    count, _, statistics, _ = cv2.connectedComponentsWithStats(mask)
    minimum_area = max(80, round((right - left) * (bottom - top) * MIN_COMPONENT_FRACTION))
    regions = []
    for x, y, width, height, area in statistics[1:count]:
        if area < minimum_area or width < 6 or height < 6:
            continue
        before = gray_ref[y:y + height, x:x + width]
        after = gray_cur[y:y + height, x:x + width]
        before_edges = float((cv2.Canny(before, 40, 100) > 0).mean())
        after_edges = float((cv2.Canny(after, 40, 100) > 0).mean())
        if before_edges < 0.006:
            continue
        std_loss = 1 - float(after.std()) / max(float(before.std()), 1.0)
        edge_loss = 1 - after_edges / max(before_edges, 0.001)
        texture_loss = float(np.clip(max(std_loss, edge_loss), 0, 1))
        regions.append({"box": [int(x), int(y), int(x + width), int(y + height)],
                        "changed_pixels": int(area), "texture_loss": round(texture_loss, 4),
                        "changed_fraction": round(float(area / (width * height)), 4),
                        "status": "gap" if texture_loss >= MIN_TEXTURE_LOSS else "uncertain"})
    return regions
