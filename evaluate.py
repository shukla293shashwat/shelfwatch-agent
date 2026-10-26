"""Evaluate one named dataset at a time; keep development and test evidence separate."""
import argparse
import csv
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import cv2
from shelfwatch import agent

ROOT = Path(__file__).resolve().parent


def parse_cells(value):
    return {tuple(map(int, item.strip().split('-'))) for item in value.split(';') if item.strip()}


def overlap(a, b):
    left, top, right, bottom = max(a[0],b[0]), max(a[1],b[1]), min(a[2],b[2]), min(a[3],b[3])
    intersection = max(0,right-left) * max(0,bottom-top)
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union else 0


def match_regions(expected, predicted):
    options = sorted(((overlap(a,b),i,j) for i,a in enumerate(expected) for j,b in enumerate(predicted)), reverse=True)
    used_truth, used_prediction = set(), set()
    for score, i, j in options:
        if score >= .25 and i not in used_truth and j not in used_prediction:
            used_truth.add(i)
            used_prediction.add(j)
    return len(used_truth), len(predicted)-len(used_prediction), len(expected)-len(used_truth)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--labels', type=Path, default=ROOT/'samples/eval/labels.csv')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/evaluation.json')
    parser.add_argument('--kind', choices=['development','synthetic_stress','annotated_preview','real_labeled'], default='development')
    args = parser.parse_args()
    labels = args.labels.resolve()
    with labels.open(newline='', encoding='utf-8-sig') as file:
        dataset = list(csv.DictReader(file))
    if not dataset:
        raise SystemExit('The label file is empty.')
    cases, totals, region_totals = [], [0,0,0], [0,0,0]
    for row in dataset:
        reference_path = labels.parent/row['reference'] if row.get('reference') else ROOT/'samples/reference.jpg'
        current_path = labels.parent/row['image']
        reference, current = cv2.imread(str(reference_path)), cv2.imread(str(current_path))
        if reference is None or current is None:
            raise SystemExit(f'Could not load {reference_path} or {current_path}')
        truth = parse_cells(row.get('gap_cells',''))
        expected_review = parse_cells(row.get('review_cells',''))
        roi = json.loads(row['roi']) if row.get('roi') else None
        started = time.perf_counter()
        result = agent.run(reference,current,int(row.get('rows') or 3),int(row.get('cols') or 6),roi=roi,persist=False)
        elapsed = round(time.perf_counter()-started,4)
        predicted = set(result['gaps'])
        review = set(result['uncertain'])
        counts = [len(truth&predicted),len(predicted-truth),len(truth-predicted)]
        totals = [a+b for a,b in zip(totals,counts)]
        expected_status = row.get('expected_status','')
        expected_regions = json.loads(row['region_boxes']) if row.get('region_boxes') else None
        region_counts = None
        if expected_regions is not None:
            region_counts = match_regions(expected_regions,[r['box'] for r in result['regions'] if r['status']=='gap'])
            region_totals = [a+b for a,b in zip(region_totals,region_counts)]
            passed = region_counts[1:] == (0,0)
        else:
            passed = predicted==truth and review==expected_review
        passed = passed and (not expected_status or result['status']==expected_status)
        cases.append({'image':row['image'],'reference':reference_path.name,'source':row.get('source','generated demo'),
                      'split':row.get('split',args.kind),'input_sha256':hashlib.sha256(current_path.read_bytes()).hexdigest(),
                      'reference_sha256':hashlib.sha256(reference_path.read_bytes()).hexdigest(),
                      'expected_status':expected_status,'actual_status':result['status'],
                      'expected_gaps':sorted(map(list,truth)),'predicted_gaps':sorted(map(list,predicted)),
                      'expected_review':sorted(map(list,expected_review)),'actual_review':sorted(map(list,review)),
                      'regions':result['regions'],'region_counts':region_counts,
                      'confidence':round(result['confidence'],4),'seconds':elapsed,'pass':passed,'trace':result['trace']})
    tp,fp,fn = totals
    precision = tp/(tp+fp) if tp+fp else None
    recall = tp/(tp+fn) if tp+fn else None
    f1 = 2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None
    report = {'generated_at_utc':datetime.now(UTC).isoformat(),'opencv_version':cv2.__version__,'dataset_kind':args.kind,
              'label_sha256':hashlib.sha256(labels.read_bytes()).hexdigest(),
              'source_hashes':{str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in (ROOT/'shelfwatch/agent.py',ROOT/'shelfwatch/vision.py')},
              'image_count':len(cases),'passed_cases':sum(c['pass'] for c in cases),'all_cases_pass':all(c['pass'] for c in cases),
              'cell_metrics':{'tp':tp,'fp':fp,'fn':fn,'precision':precision,'recall':recall,'f1':f1} if args.kind!='annotated_preview' else None,
              'manual_region_diagnostics':{'tp':region_totals[0],'fp':region_totals[1],'fn':region_totals[2],'iou_threshold':.25} if args.kind=='annotated_preview' else None,
              'mean_seconds':round(sum(c['seconds'] for c in cases)/len(cases),4),
              'limits':'Generated stress tests are not retail accuracy evidence. Annotated publisher previews contain visible labels and are only a separate diagnostic. No product-count metric is inferred from grid cells or merged change regions.',
              'cases':cases}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(f"{args.kind}: {report['passed_cases']}/{len(cases)} cases passed; {report['mean_seconds']} seconds/image")
    if report['cell_metrics']:
        print('Cell metrics:', report['cell_metrics'])
    if report['manual_region_diagnostics']:
        print('Annotated-preview region diagnostics:',report['manual_region_diagnostics'])
    for case in cases:
        if not case['pass']:
            print('FAIL',case['image'],case['actual_status'],'gaps=',case['predicted_gaps'],'review=',case['actual_review'])
    print('Saved:',args.output)
    return 0 if report['all_cases_pass'] else 1


if __name__=='__main__':
    raise SystemExit(main())
