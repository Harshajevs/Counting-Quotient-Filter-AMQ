#!/usr/bin/env python3
"""Verify binary workload cardinality/disjointness outside benchmark timings."""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def audit_pair(positive_path, negative_path, declared_distinct):
    positive_path, negative_path = Path(positive_path), Path(negative_path)
    for path in (positive_path, negative_path):
        if path.stat().st_size == 0 or path.stat().st_size % 8:
            raise ValueError(f'invalid uint64 binary workload: {path}')
    values = np.fromfile(positive_path, dtype='<u8')
    values.sort()
    distinct = int(np.count_nonzero(values[1:] != values[:-1])) + 1
    if distinct != int(declared_distinct):
        raise ValueError(f'distinct count mismatch: declared={declared_distinct}, actual={distinct}')
    maximum = 1
    if distinct != values.size:
        changes = np.flatnonzero(values[1:] != values[:-1]) + 1
        maximum = int(np.diff(np.r_[0, changes, values.size]).max())
    negative_count = 0
    with negative_path.open('rb') as stream:
        while True:
            batch = np.fromfile(stream, dtype='<u8', count=1_000_000)
            if not batch.size:
                break
            idx = np.searchsorted(values, batch)
            valid = idx < values.size
            if np.any(values[idx[valid]] == batch[valid]):
                raise ValueError('negative query stream contains an inserted key')
            negative_count += int(batch.size)
    return dict(positive_count=int(values.size), distinct_keys=distinct,
                max_frequency=maximum, negative_count=negative_count,
                positive_sha256=digest(positive_path), negative_sha256=digest(negative_path),
                negative_overlap=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    root = args.directory
    manifest = dict(line.split('=', 1) for line in (root/'manifest.txt').read_text().splitlines() if '=' in line)
    report = {}
    for label, stem in [('uniform', 'uniform'), ('zipfian', 'zipf')]:
        declared = manifest['uniform_distinct_keys' if stem == 'uniform' else 'zipf_distinct_keys']
        report[label] = audit_pair(root/f'{stem}_positive.bin', root/f'{stem}_negative.bin', declared)
        if report[label]['positive_count'] != int(manifest['n']) or report[label]['negative_count'] != int(manifest['neg']):
            raise ValueError('workload length differs from manifest')
        print(f"PASS {label}: {report[label]['positive_count']:,} operations; {declared} distinct; no negative overlap")
    (root/'audit.json').write_text(json.dumps(report, indent=2)+'\n')

if __name__ == '__main__':
    main()
