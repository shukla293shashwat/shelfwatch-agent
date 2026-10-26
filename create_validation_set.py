"""Generate a separate, labelled stress set with seeds unused by the demo."""
import csv
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'samples' / 'validation'


def reference_image(seed):
    random = np.random.default_rng(seed)
    image = np.full((480, 720, 3), 185, dtype=np.uint8)
    for row in range(3):
        for col in range(6):
            x, y = col * 120 + 12, row * 160 + 12
            color = tuple(int(v) for v in random.integers(25, 220, 3))
            cv2.rectangle(image, (x, y), (x + 96, y + 136), color, -1)
            for _ in range(32):
                point = (int(random.integers(x + 3, x + 93)), int(random.integers(y + 3, y + 133)))
                cv2.circle(image, point, int(random.integers(2, 7)), tuple(int(v) for v in random.integers(0, 255, 3)), -1)
            cv2.putText(image, f'{row}{col}', (x + 5, y + 40), cv2.FONT_HERSHEY_SIMPLEX, .7, (245, 245, 245), 2)
    return image


def remove(image, cells):
    result = image.copy()
    for row, col in cells:
        cv2.rectangle(result, (col * 120, row * 160), ((col + 1) * 120 - 1, (row + 1) * 160 - 1), (185, 185, 185), -1)
    return result


def main():
    OUTPUT.mkdir(exist_ok=True)
    labels = []
    for seed in (73, 91, 137):
        ref = reference_image(seed)
        ref_name = f'reference_{seed}.jpg'
        cv2.imwrite(str(OUTPUT / ref_name), ref)
        perspective = cv2.getPerspectiveTransform(np.float32([[0,0],[719,0],[719,479],[0,479]]), np.float32([[3,2],[716,4],[718,476],[2,478]]))
        partial = ref.copy()
        cv2.rectangle(partial, (3 * 120, 160), (3 * 120 + 59, 319), (185, 185, 185), -1)
        random = np.random.default_rng(seed + 1000)
        cases = [
            ('unchanged', ref.copy(), [], [], 'shelf_ok', None),
            ('brightness', cv2.convertScaleAbs(ref, alpha=1, beta=12), [], [], 'shelf_ok', None),
            ('viewpoint', cv2.warpPerspective(ref, perspective, (720, 480)), [], [], 'shelf_ok', None),
            ('single_gap', remove(ref, [(0,1)]), [(0,1)], [], 'awaiting_approval', None),
            ('two_gaps', remove(ref, [(1,2),(2,4)]), [(1,2),(2,4)], [], 'awaiting_approval', None),
            ('three_gaps', remove(ref, [(0,4),(1,1),(2,3)]), [(0,4),(1,1),(2,3)], [], 'awaiting_approval', None),
            ('partial_occlusion', partial, [], [(1,3)], 'needs_review', None),
            ('uniform_bad_photo', np.full_like(ref, 200), [], [], 'recapture_requested', None),
            ('unrelated_scene', random.integers(0,255,ref.shape,dtype=np.uint8), [], [], 'recapture_requested', None),
            ('shelf_out_of_frame', ref[:, :540].copy(), [], [], 'recapture_requested', None),
            ('change_outside_roi', remove(ref, [(2,5)]), [], [], 'shelf_ok', [0,0,1,2/3]),
        ]
        for name, current, gaps, review, expected, roi in cases:
            image_name = f'{seed}_{name}.jpg'
            cv2.imwrite(str(OUTPUT / image_name), current)
            labels.append({'reference': ref_name, 'image': image_name,
                           'gap_cells': ';'.join(f'{r}-{c}' for r,c in gaps),
                           'review_cells': ';'.join(f'{r}-{c}' for r,c in review),
                           'expected_status': expected, 'rows': 2 if roi else 3, 'cols': 6,
                           'roi': json.dumps(roi) if roi else '',
                           'source': 'generated stress fixture', 'split': 'held-out synthetic',
                           'notes': name})
    with (OUTPUT / 'labels.csv').open('w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=labels[0].keys())
        writer.writeheader()
        writer.writerows(labels)
    print(f'Generated {len(labels)} cases from three references; not real-store data.')


if __name__ == '__main__':
    main()
