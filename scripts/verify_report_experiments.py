#!/usr/bin/env python3
"""Reject partial or stale supplementary CQF runs before report completion."""
import csv
from pathlib import Path


def require_full_cqf_rows(path, expected_rows, expected_n):
    with Path(path).open(newline='') as stream:
        rows=list(csv.DictReader(stream))
    if len(rows) != expected_rows:
        raise ValueError(f'{path}: expected {expected_rows} rows, found {len(rows)}')
    for row in rows:
        if any(int(row[field]) != expected_n for field in ['n_requested','n_inserted','found_positive']):
            raise ValueError(f'{path}: incomplete supplementary CQF run: {row}')
    return rows


def main():
    root=Path('results/report')
    compact=require_full_cqf_rows(root/'compact_zipf_raw.csv',1,67_000_000)
    if int(compact[0]['deleted_ok']) != 67_000_000:
        raise ValueError('compact Zipf deletions incomplete')
    rows=require_full_cqf_rows(root/'geometry_control_raw.csv',6,63_753_420)
    for q in [26,27]:
        if sum(row['config_param'].startswith(f'qbits={q};') for row in rows) != 3:
            raise ValueError(f'geometry control needs exactly three qbits={q} repetitions')
    print('PASS: complete compact Zipf run and six complete matched-N geometry rows')

if __name__=='__main__':main()
