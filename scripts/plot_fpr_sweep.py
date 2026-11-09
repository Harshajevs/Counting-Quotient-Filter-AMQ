#!/usr/bin/env python3
"""Compare throughput and measured FPR across paper-scale target settings."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'extended'
tags = ['1_256', '1_512', '1_1024']
targets = ['1/256', '1/512', '1/1024']
all_rows = {}
for tag in tags:
    p = OUT / f'paper_scale_{tag}.csv'
    if not p.exists():
        raise SystemExit(f'Missing {p}; run scripts/run_fpr_sweep.sh first')
    all_rows[tag] = list(csv.DictReader(p.open()))

filters = ['bloom', 'cuckoo', 'cqf']
labels = ['Bloom', 'Cuckoo', 'CQF']
def complete(r):
    return int(r['n_inserted']) == int(r['n_requested'])

for dist in ['uniform', 'zipfian']:
    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(filters))
    width = .23
    for j, tag in enumerate(tags):
        rr = {r['filter']: r for r in all_rows[tag] if r['distribution'] == dist}
        for i, filt in enumerate(filters):
            r = rr[filt]
            invalid = filt == 'cuckoo' and dist == 'zipfian' and not complete(r)
            if not invalid:
                ax.bar(x[i] + (j - 1) * width, float(r['insert_ops_sec']) / 1e6,
                       width, color=['#4472C4', '#ED7D31', '#70AD47'][j],
                       label=targets[j] if i == 0 else None)
    tick_labels = labels.copy()
    if dist == 'zipfian':
        tick_labels[1] = 'Cuckoo\n(failed: 24)'
    ax.set_xticks(x, tick_labels)
    ax.set_ylabel('Insert throughput (M operations/s)')
    ax.set_title(f'Paper-scale insertion throughput — {dist.title()}')
    ax.grid(axis='y', alpha=.25)
    ax.legend(title='Target FPR')
    fig.tight_layout()
    fig.savefig(OUT / f'paper_scale_fpr_sweep_{dist}_insert.png', dpi=180)
    plt.close(fig)

# Use a log scale to show Zipfian rates without flattening them against the
# uniform rates. Zero observations and failed Cuckoo rows are labelled.
fig, axs = plt.subplots(1, 2, figsize=(12, 5.2), sharey=False)
for ax, dist in zip(axs, ['uniform', 'zipfian']):
    for filt in filters:
        vals = []
        for tag in tags:
            r = next(r for r in all_rows[tag] if r['distribution'] == dist and r['filter'] == filt)
            vals.append(float(r['measured_fp_rate']) if complete(r) or filt != 'cuckoo' else np.nan)
        if np.isfinite(vals).any() and any(v > 0 for v in vals if np.isfinite(v)):
            ax.plot(targets, [v if v > 0 else np.nan for v in vals], marker='o', label=filt.upper())
    if dist == 'zipfian':
        ax.text(.03, .12, 'Bloom: 0 observed at all targets', transform=ax.transAxes, fontsize=8)
        ax.text(.03, .04, 'Cuckoo: failed after 24 inserts', transform=ax.transAxes, fontsize=8)
    ax.set_yscale('log')
    ax.set_ylim(1e-7, 1e-2)
    ax.set_title(dist.title())
    ax.set_ylabel('Measured false-positive rate (log scale)')
    ax.grid(True, alpha=.25, which='both')
    ax.tick_params(axis='x', rotation=15)
axs[0].legend()
fig.suptitle('Measured FPR across configured targets')
fig.tight_layout()
fig.savefig(OUT / 'paper_scale_fpr_sweep_accuracy.png', dpi=180)
plt.close(fig)
print('FPR-sweep plots written to', OUT)
