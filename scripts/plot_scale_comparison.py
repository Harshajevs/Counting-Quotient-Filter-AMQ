#!/usr/bin/env python3
"""Compare cache-sized Phase-1 runs with the 67M paper-scale run."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'results' / 'bench.csv'
LARGE = ROOT / 'results' / 'extended' / 'paper_scale_1_512.csv'
OUT = ROOT / 'results' / 'extended'
if not BASE.exists() or not LARGE.exists():
    raise SystemExit('Need results/bench.csv and results/extended/paper_scale_1_512.csv first')

def read(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))

def complete(r):
    return int(r['n_inserted']) == int(r['n_requested'])

base = {(r['filter'], r['distribution']): r for r in read(BASE)}
large = {(r['filter'], r['distribution']): r for r in read(LARGE)}
filters = ['bloom', 'cuckoo', 'cqf']
dists = ['uniform', 'zipfian']
metrics = [
    ('insert_ops_sec', 'Insert'),
    ('query_pos_ops_sec', 'Positive lookup'),
    ('query_neg_ops_sec', 'Negative lookup'),
    ('delete_ops_sec', 'Delete'),
]

rows = []
for metric, label in metrics:
    for dist in dists:
        for filt in filters:
            b = base[(filt, dist)]
            l = large[(filt, dist)]
            unsupported = metric == 'delete_ops_sec' and filt == 'bloom'
            valid_b = complete(b) and not unsupported
            valid_l = complete(l) and not unsupported
            bval = float(b[metric]) if valid_b else None
            lval = float(l[metric]) if valid_l else None
            ratio = lval / bval if (bval is not None and lval is not None and bval > 0) else None
            rows.append({
                'metric': label,
                'distribution': dist,
                'filter': filt,
                'baseline_996k_ops_sec': f'{bval:.4f}' if bval is not None else 'NA',
                'paper_scale_67m_ops_sec': f'{lval:.4f}' if lval is not None else 'NA',
                'large_vs_baseline_ratio': f'{ratio:.4f}' if ratio is not None else 'NA',
                'baseline_n_inserted': str(b['n_inserted']),
                'baseline_n_requested': str(b['n_requested']),
                'large_n_inserted': str(l['n_inserted']),
                'large_n_requested': str(l['n_requested']),
            })
with (OUT / 'scale_comparison.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)

# Plot only full-workload throughput. Cuckoo/Zipf is marked failed rather than
# showing a misleading rate based on 24 accepted operations; Bloom delete is N/A.
fig, axs = plt.subplots(2, 2, figsize=(14, 9))
for ax, (metric, title) in zip(axs.flat, metrics):
    cats = [(d, f) for d in dists for f in filters]
    x = np.arange(len(cats))
    width = .36
    for i, (dist, filt) in enumerate(cats):
        b = base[(filt, dist)]
        l = large[(filt, dist)]
        unsupported = metric == 'delete_ops_sec' and filt == 'bloom'
        valid_b = complete(b) and not unsupported
        valid_l = complete(l) and not unsupported
        if valid_b:
            ax.bar(i - width/2, float(b[metric]) / 1e6, width, color='#4472C4',
                   label='Baseline (996k)' if i == 0 else None)
        if valid_l:
            ax.bar(i + width/2, float(l[metric]) / 1e6, width, color='#ED7D31',
                   label='Paper scale (67M)' if i == 0 else None)
    tick_labels = []
    for dist, filt in cats:
        label = f'{dist[:1].upper()}-{filt.upper()}'
        if metric == 'delete_ops_sec' and filt == 'bloom':
            label += '\n(no delete)'
        elif filt == 'cuckoo' and dist == 'zipfian':
            label += '\n(failed: 24)'
        tick_labels.append(label)
    ax.set_xticks(x, tick_labels, fontsize=8)
    ax.set_ylabel('Million operations / second')
    ax.set_title(title)
    ax.grid(axis='y', alpha=.25)
axs[0, 0].legend(fontsize=8)
fig.suptitle('Cache-sized baseline vs 67M paper-scale workload (same 1/512 target)')
fig.tight_layout()
fig.savefig(OUT / 'scale_comparison_throughput.png', dpi=180)
plt.close(fig)

# Memory comparison is meaningful for the completed uniform runs.
fig, ax = plt.subplots(figsize=(8.5, 5))
x = np.arange(3)
width = .36
bmem = [int(base[(f, 'uniform')]['memory_bytes']) / 1e6 for f in filters]
lmem = [int(large[(f, 'uniform')]['memory_bytes']) / 1e6 for f in filters]
ax.bar(x - width/2, bmem, width, color='#4472C4', label='Baseline (996k)')
ax.bar(x + width/2, lmem, width, color='#ED7D31', label='Paper scale (67M)')
ax.set_xticks(x, [f.upper() for f in filters])
ax.set_ylabel('Allocated filter memory (MB)')
ax.set_title('Filter footprint: cache-sized vs paper-scale')
ax.grid(axis='y', alpha=.25)
ax.legend()
fig.tight_layout()
fig.savefig(OUT / 'scale_comparison_memory.png', dpi=180)
plt.close(fig)

# FPR comparison uses log axes. Zero observations are annotated; the Cuckoo
# Zipf point is N/A for both scales because neither run accepted all operations.
fig, axs = plt.subplots(1, 2, figsize=(11, 5), sharey=False)
for ax, dist in zip(axs, dists):
    x = np.arange(3)
    width = .36
    for i, filt in enumerate(filters):
        b = base[(filt, dist)]
        l = large[(filt, dist)]
        invalid = not complete(b) or not complete(l)
        if invalid:
            continue
        for offset, r, label in [(-width/2, b, 'Baseline measured'),
                                 (width/2, l, '67M measured')]:
            value = float(r['measured_fp_rate'])
            if value > 0:
                ax.bar(i + offset, value, width, color=('#4472C4' if label == 'Baseline measured' else '#ED7D31'),
                       label=label if i == 0 else None)
    tick_labels = [f.upper() for f in filters]
    if dist == 'zipfian':
        tick_labels[0] = 'BLOOM\n(0 observed)'
        tick_labels[1] = 'CUCKOO\n(N/A: failed 24)'
    ax.set_yscale('log')
    ax.set_ylim(1e-8, 1e-2)
    ax.set_xticks(x, tick_labels, fontsize=8)
    ax.set_title(dist.title())
    ax.grid(axis='y', which='both', alpha=.25)
axs[0].set_ylabel('Measured false-positive rate (log scale)')
axs[0].legend(fontsize=8)
fig.suptitle('Observed FPR: Phase-1 vs 67M (Cuckoo/Zipf not comparable after failure)')
fig.tight_layout()
fig.savefig(OUT / 'scale_comparison_fpr.png', dpi=180)
plt.close(fig)
print('Wrote scale comparison CSV and plots to', OUT)
