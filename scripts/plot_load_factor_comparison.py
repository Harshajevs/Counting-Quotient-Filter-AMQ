#!/usr/bin/env python3
"""Compare the 67M CQF sizing point with a near-95%-load companion point."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'extended'
FILES = {
    '67M / 50% load': OUT / 'paper_scale_1_512.csv',
    '63.75M / 95% load': OUT / 'paper_scale_highload_1_512.csv',
}

def read_csv(path):
    with path.open(newline='') as f:
        return list(csv.DictReader(f))

def read_config(path):
    return dict(line.strip().split('=', 1) for line in path.read_text().splitlines() if '=' in line)

records = []
for label, csv_path in FILES.items():
    cfg_path = csv_path.with_name(csv_path.stem + '_configuration.txt')
    if not csv_path.exists() or not cfg_path.exists():
        raise SystemExit(f'Missing {csv_path} or {cfg_path}; run the two 1/512 configurations first')
    cfg = read_config(cfg_path)
    rows = {(r['filter'], r['distribution']): r for r in read_csv(csv_path)}
    qbits = int(cfg['cqf_qbits'])
    slots = int(cfg['cqf_slots'])
    for dist in ['uniform', 'zipfian']:
        cqf = rows[('cqf', dist)]
        records.append({
            'configuration': label,
            'distribution': dist,
            'operations': cqf['n_requested'],
            'distinct_keys': cfg['uniform_distinct_keys'] if dist == 'uniform' else cfg['zipf_distinct_keys'],
            'cqf_qbits': qbits,
            'cqf_slots': slots,
            'distinct_load_factor': f'{int(cfg["uniform_distinct_keys"] if dist == "uniform" else cfg["zipf_distinct_keys"])/slots:.8f}',
            'cqf_memory_bytes': cqf['memory_bytes'],
            'insert_ops_sec': cqf['insert_ops_sec'],
            'positive_lookup_ops_sec': cqf['query_pos_ops_sec'],
            'negative_lookup_ops_sec': cqf['query_neg_ops_sec'],
            'delete_ops_sec': cqf['delete_ops_sec'],
            'measured_fpr': cqf['measured_fp_rate'],
            'theoretical_fpr': cqf['theoretical_fp_rate'],
        })

with (OUT / 'cqf_load_factor_comparison.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(records[0]))
    writer.writeheader()
    writer.writerows(records)

labels = list(FILES)
colors = ['#4472C4', '#ED7D31']

# Memory / bits per requested operation at the uniform operating point.
uniform = [next(r for r in records if r['configuration'] == label and r['distribution'] == 'uniform') for label in labels]
fig, axs = plt.subplots(1, 2, figsize=(10.5, 4.8))
mem_mb = [int(r['cqf_memory_bytes']) / 1e6 for r in uniform]
bits_per_item = [int(r['cqf_memory_bytes']) * 8 / int(r['operations']) for r in uniform]
for ax, values, ylabel, title in [
    (axs[0], mem_mb, 'Allocated memory (MB)', 'CQF memory footprint'),
    (axs[1], bits_per_item, 'Bits per requested item', 'CQF memory per item'),
]:
    ax.bar(labels, values, color=colors)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.tick_params(axis='x', rotation=12)
    ax.grid(axis='y', alpha=.25)
fig.suptitle('CQF capacity rounding: 67M vs near-95% occupancy')
fig.tight_layout()
fig.savefig(OUT / 'cqf_load_factor_memory.png', dpi=180)
plt.close(fig)

# Throughput comparison by workload and operation.
metrics = [
    ('insert_ops_sec', 'Insert'),
    ('positive_lookup_ops_sec', 'Positive lookup'),
    ('negative_lookup_ops_sec', 'Negative lookup'),
    ('delete_ops_sec', 'Delete'),
]
fig, axs = plt.subplots(2, 2, figsize=(12, 8))
for ax, (metric, title) in zip(axs.flat, metrics):
    for i, dist in enumerate(['uniform', 'zipfian']):
        rr = [next(r for r in records if r['configuration'] == label and r['distribution'] == dist) for label in labels]
        vals = [float(r[metric]) / 1e6 for r in rr]
        ax.bar(np.arange(2) + (i - .5) * .34, vals, .34,
               color=('#4472C4' if dist == 'uniform' else '#ED7D31'),
               label=dist.title() if ax is axs.flat[0] else None)
    ax.set_xticks(np.arange(2), ['67M / 50%', '63.75M / 95%'])
    ax.set_ylabel('Million operations / second')
    ax.set_title(title)
    ax.grid(axis='y', alpha=.25)
axs[0, 0].legend()
fig.suptitle('CQF throughput at two capacity/load operating points')
fig.tight_layout()
fig.savefig(OUT / 'cqf_load_factor_throughput.png', dpi=180)
plt.close(fig)

# Accuracy comparison with independent scales for uniform and Zipfian data.
fig, axs = plt.subplots(1, 2, figsize=(11, 4.8), sharey=False)
for ax, dist in zip(axs, ['uniform', 'zipfian']):
    rr = [next(r for r in records if r['configuration'] == label and r['distribution'] == dist) for label in labels]
    x = np.arange(2)
    measured = [float(r['measured_fpr']) for r in rr]
    theory = [float(r['theoretical_fpr']) for r in rr]
    ax.bar(x - .18, measured, .36, color='#4472C4', label='Measured')
    ax.bar(x + .18, theory, .36, color='#ED7D31', label='Theoretical')
    ax.set_yscale('log')
    ax.set_ylim(1e-7, 1e-2 if dist == 'uniform' else 2e-5)
    ax.set_xticks(x, ['67M / 50%', '63.75M / 95%'])
    ax.set_title(dist.title())
    ax.grid(axis='y', which='both', alpha=.25)
axs[0].set_ylabel('False-positive rate (log scale)')
axs[0].legend()
fig.suptitle('CQF measured vs theoretical FPR at two load factors')
fig.tight_layout()
fig.savefig(OUT / 'cqf_load_factor_fpr.png', dpi=180)
plt.close(fig)
print('Wrote CQF load-factor comparison CSV and plots to', OUT)
