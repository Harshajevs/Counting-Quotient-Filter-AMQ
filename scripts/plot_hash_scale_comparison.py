#!/usr/bin/env python3
"""Compare CQF hash-mode measurements at the 996k control and 67M scale."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results' / 'extended'
CONTROL = list(csv.DictReader((OUT / 'hash_modes.csv').open()))
LARGE = list(csv.DictReader((OUT / 'hash_modes_67m.csv').open()))
MODES = ['default', 'invertible', 'none']
DISTS = ['uniform', 'zipfian']
METRICS = [
    ('insert_ops_sec', 'Insertion'),
    ('query_pos_ops_sec', 'Positive lookup'),
    ('query_neg_ops_sec', 'Negative lookup'),
]

def mode_of(row):
    return row['config_param'].split('hash=', 1)[1].split(';', 1)[0]

def index_rows(rows):
    return {(r['distribution'], mode_of(r)): r for r in rows}

small = index_rows(CONTROL)
large = index_rows(LARGE)
fields = [
    'distribution', 'hash_mode', 'control_operations', 'large_operations',
    'control_insert_mops', 'large_insert_mops', 'insert_scale_ratio',
    'control_positive_lookup_mops', 'large_positive_lookup_mops', 'positive_lookup_scale_ratio',
    'control_negative_lookup_mops', 'large_negative_lookup_mops', 'negative_lookup_scale_ratio',
    'control_measured_fpr', 'large_measured_fpr',
    'control_expected_fpr', 'large_expected_fpr',
    'control_qbits', 'large_qbits', 'control_rbits', 'large_rbits',
]
rows_out = []
for dist in DISTS:
    for mode in MODES:
        a, b = small[(dist, mode)], large[(dist, mode)]
        vals = {
            'distribution': dist,
            'hash_mode': mode,
            'control_operations': a['n_requested'],
            'large_operations': b['n_requested'],
            'control_measured_fpr': a['measured_fp_rate'],
            'large_measured_fpr': b['measured_fp_rate'],
            'control_expected_fpr': a['theoretical_fp_rate'],
            'large_expected_fpr': b['theoretical_fp_rate'],
            'control_qbits': a['config_param'].split('qbits=')[1].split(';')[0],
            'large_qbits': b['config_param'].split('qbits=')[1].split(';')[0],
            'control_rbits': a['config_param'].split('rbits=')[1].split(';')[0],
            'large_rbits': b['config_param'].split('rbits=')[1].split(';')[0],
        }
        for key, _ in METRICS:
            field = {
                'insert_ops_sec': 'insert',
                'query_pos_ops_sec': 'positive_lookup',
                'query_neg_ops_sec': 'negative_lookup',
            }[key]
            x, y = float(a[key]) / 1e6, float(b[key]) / 1e6
            vals[f'control_{field}_mops'] = f'{x:.6f}'
            vals[f'large_{field}_mops'] = f'{y:.6f}'
            vals[f'{field}_scale_ratio'] = f'{y/x:.6f}' if x else 'NA'
        rows_out.append(vals)
with (OUT / 'hash_scale_comparison.csv').open('w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows_out)

# Paired scale comparison. Note that QF geometry changes with scale, so this
# is a scale/configuration comparison, not a pure isolated cache experiment.
fig, axs = plt.subplots(2, 3, figsize=(15, 8), sharex='col')
width = 0.36
x = np.arange(3)
labels = ['DEFAULT\n(Murmur64A)', 'INVERTIBLE\n(hash_64)', 'NONE\n(SplitMix64)']
for i, dist in enumerate(DISTS):
    rr = [r for r in rows_out if r['distribution'] == dist]
    for j, (key, title) in enumerate(METRICS):
        ax = axs[i, j]
        metric = {'insert_ops_sec':'insert', 'query_pos_ops_sec':'positive_lookup', 'query_neg_ops_sec':'negative_lookup'}[key]
        baseline = [float(r[f'control_{metric}_mops']) for r in rr]
        large_vals = [float(r[f'large_{metric}_mops']) for r in rr]
        ax.bar(x - width/2, baseline, width, label='996k control')
        ax.bar(x + width/2, large_vals, width, label='67M operations')
        ax.set_title(title)
        ax.set_ylabel('M operations/s')
        ax.set_xticks(x, labels)
        ax.grid(axis='y', alpha=.25)
        if i == 0 and j == 0:
            ax.legend()
        if j == 0:
            ax.set_ylabel(f'{dist.title()}\nM operations/s')
fig.suptitle('CQF hash-mode throughput across scales\n(geometry: 996k uses qbits=20; 67M uses qbits=27)')
fig.tight_layout()
fig.savefig(OUT / 'hash_scale_comparison_throughput.png', dpi=180)
plt.close(fig)
print('Wrote hash-scale comparison CSV and plot to', OUT)
