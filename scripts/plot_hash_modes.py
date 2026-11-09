#!/usr/bin/env python3
"""Plots CQF hash-mode throughput (with repeat variability) and FPR accuracy."""
import csv
import sys
from collections import defaultdict
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'extended'
tag = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else ''
stem = f'hash_modes_{tag}' if tag else 'hash_modes'
AGG = list(csv.DictReader((OUT / f'{stem}.csv').open()))
RAW_PATH = OUT / f'{stem}_raw.csv'
RAW = list(csv.DictReader(RAW_PATH.open())) if RAW_PATH.exists() else AGG
suffix = f'_{tag}' if tag else ''
if not AGG:
    raise SystemExit('Run scripts/run_hash_study.sh first')

modes = ['default', 'invertible', 'none']
labels = ['DEFAULT\n(Murmur64A)', 'INVERTIBLE\n(hash_64)', 'NONE\n(external SplitMix64)']
metrics = [
    ('insert_ops_sec', 'Insert'),
    ('query_pos_ops_sec', 'Positive lookup'),
    ('query_neg_ops_sec', 'Negative lookup'),
]
# Deletion can be omitted by design in very large hash-mode runs, where it is
# not needed to measure the cost of hashing in insert/lookup/FPR paths.
if all(r.get('delete_ops_sec', '').strip().upper() not in ('NA', 'N/A', '') for r in AGG):
    metrics.append(('delete_ops_sec', 'Delete'))

# Throughput plots show mean +/- one sample standard deviation across repeats.
for dist in ['uniform', 'zipfian']:
    rr = [r for r in AGG if r['distribution'] == dist]
    rr.sort(key=lambda r: modes.index(r['config_param'].split('hash=')[-1].split(';')[0]))
    raw_by_mode = defaultdict(list)
    for r in RAW:
        if r['distribution'] == dist:
            mode = r['config_param'].split('hash=')[-1].split(';')[0]
            raw_by_mode[mode].append(r)
    x = np.arange(3)
    w = .19
    fig, ax = plt.subplots(figsize=(10, 5.5))
    for j, (key, label) in enumerate(metrics):
        vals, errs = [], []
        for mode in modes:
            sample = [float(r[key]) / 1e6 for r in raw_by_mode[mode] if r.get(key, '').strip().upper() not in ('NA', 'N/A', '')]
            vals.append(float(np.mean(sample)) if sample else 0.0)
            errs.append(float(np.std(sample, ddof=1)) if len(sample) > 1 else 0.0)
        ax.bar(x + (j - 1.5) * w, vals, w, yerr=errs, capsize=3, label=label)
    ax.set_xticks(x, labels)
    ax.set_ylabel('Throughput (million operations/s)')
    title_suffix = ' (delete omitted)' if len(metrics) == 3 else ''
    ax.set_title(f'CQF hash-mode end-to-end throughput — {dist.title()} workload{title_suffix}')
    ax.grid(axis='y', alpha=.25)
    ax.legend(ncol=2)
    fig.tight_layout()
    fig.savefig(OUT / f'hash_throughput_{dist}{suffix}.png', dpi=180)
    plt.close(fig)

# Keep a common log-scale range to avoid exaggerating tiny differences in each panel.
fig, axs = plt.subplots(1, 2, figsize=(12, 5.3), sharey=True)
for ax, dist in zip(axs, ['uniform', 'zipfian']):
    rr = [r for r in AGG if r['distribution'] == dist]
    rr.sort(key=lambda r: modes.index(r['config_param'].split('hash=')[-1].split(';')[0]))
    x = np.arange(3)
    w = .34
    measured = [max(float(r['measured_fp_rate']), 1e-10) for r in rr]
    theory = [max(float(r['theoretical_fp_rate']), 1e-10) for r in rr]
    ax.bar(x - w/2, measured, w, label='Measured')
    ax.bar(x + w/2, theory, w, label='Theoretical expectation')
    ax.set_yscale('log')
    ax.set_ylim(1e-7, 3e-3)
    ax.set_xticks(x, labels)
    ax.set_title(dist.title())
    ax.grid(axis='y', which='both', alpha=.25)
axs[0].set_ylabel('False-positive rate (log scale)')
axs[1].legend()
fig.suptitle('CQF hash-mode measured vs theoretical FPR')
fig.tight_layout()
fig.savefig(OUT / f'hash_false_positive_rate{suffix}.png', dpi=180)
plt.close(fig)
print('Wrote hash-mode plots to', OUT)
