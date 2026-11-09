#!/usr/bin/env python3
"""Plots for extended paper-scale results; leaves Phase-1 plots untouched."""
import csv
import sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

root = Path(__file__).resolve().parents[1]
tag = sys.argv[1] if len(sys.argv) > 1 else 'paper_scale'
p = root / 'results' / 'extended' / f'{tag}.csv'
rows = list(csv.DictReader(p.open()))
if not rows:
    raise SystemExit(f'No rows in {p}')
out = p.parent
filters = ['bloom', 'cuckoo', 'cqf']
labels = ['Bloom', 'Cuckoo', 'CQF']
dists = ['uniform', 'zipfian']

def complete(r):
    return int(r['n_inserted']) == int(r['n_requested'])

for metric, title, ylabel, filename in [
    ('insert_ops_sec', 'Insertion throughput', 'Million operations/s', 'insert_throughput.png'),
    ('query_pos_ops_sec', 'Positive lookup throughput', 'Million operations/s', 'positive_lookup_throughput.png'),
    ('query_neg_ops_sec', 'Negative lookup throughput', 'Million operations/s', 'negative_lookup_throughput.png'),
    ('delete_ops_sec', 'Deletion throughput', 'Million operations/s', 'delete_throughput.png'),
]:
    fig, ax = plt.subplots(figsize=(9, 5))
    width = .36
    x = np.arange(3)
    for i, dist in enumerate(dists):
        rr = {r['filter']: r for r in rows if r['distribution'] == dist}
        pos = x + (i - .5) * width
        labelled = False
        for j, filt in enumerate(filters):
            r = rr.get(filt)
            unavailable = (
                r is None or
                (metric == 'delete_ops_sec' and filt == 'bloom') or
                (filt == 'cuckoo' and dist == 'zipfian' and not complete(r))
            )
            if unavailable:
                continue
            ax.bar(pos[j], float(r[metric]) / 1e6, width, color=('#4472C4' if dist == 'uniform' else '#ED7D31'), label=dist.title() if not labelled else None)
            labelled = True
    tick_labels = labels.copy()
    tick_labels[1] = 'Cuckoo\n(Zipf: failed 24)'
    if metric == 'delete_ops_sec':
        tick_labels[0] = 'Bloom\n(no delete)'
    ax.set_xticks(x, tick_labels)
    ax.set_ylabel(ylabel)
    ax.set_title(title + ' — ' + tag.replace('_', ' ').title())
    if ax.containers:
        ax.legend()
    ax.grid(axis='y', alpha=.25)
    fig.tight_layout()
    fig.savefig(out / f'{tag}_{filename}', dpi=180)
    plt.close(fig)

# FPR spans several orders of magnitude under Zipf, so use log axes and
# independent panels. Values below the displayed range are explicitly annotated.
fig, axs = plt.subplots(1, 2, figsize=(12, 5.2), sharey=False)
for ax, dist in zip(axs, dists):
    rr = [r for r in rows if r['distribution'] == dist]
    rr.sort(key=lambda r: filters.index(r['filter']))
    x = np.arange(len(rr))
    width = .36
    for i, r in enumerate(rr):
        filt = r['filter']
        theory = r['theoretical_fp_rate'].strip()
        is_failed_cuckoo = filt == 'cuckoo' and dist == 'zipfian' and not complete(r)
        if is_failed_cuckoo:
            ax.text(i, 5e-8, f"N/A\n({r['n_inserted']} inserted)",
                    ha='center', va='bottom', fontsize=8)
            continue
        measured = float(r['measured_fp_rate'])
        tiny_theory = None
        if measured > 0:
            ax.bar(i - width/2, measured, width, color='#4472C4', label='Measured' if i == 0 else None)
        if theory.upper() not in ('NA', 'N/A', ''):
            v = float(theory)
            if v >= 1e-8:
                ax.bar(i + width/2, v, width, color='#ED7D31', label='Theoretical' if i == 0 else None)
            else:
                tiny_theory = v
        if dist == 'zipfian' and (measured == 0 or tiny_theory is not None):
            # Combine the two sub-axis values into one readable annotation.
            note = '0 observed' if measured == 0 else ''
            if tiny_theory is not None:
                note += ('\n' if note else '') + f'expected {tiny_theory:.1e}'
            ax.text(i, 5e-8, note, ha='center', va='bottom', fontsize=7)
    ax.set_yscale('log')
    ax.set_ylim(1e-8, 1e-2 if dist == 'uniform' else 1e-4)
    ax.set_xticks(x, [r['filter'].upper() for r in rr])
    ax.set_title(dist.title())
    ax.grid(axis='y', which='both', alpha=.25)
axs[0].set_ylabel('False-positive rate (log scale)')
axs[0].legend()
fig.suptitle('Measured vs theoretical false-positive rate — ' + tag.replace('_', ' ').title())
fig.tight_layout()
fig.savefig(out / f'{tag}_false_positive_rate.png', dpi=180)
plt.close(fig)
print('Extended plots saved in', out)
