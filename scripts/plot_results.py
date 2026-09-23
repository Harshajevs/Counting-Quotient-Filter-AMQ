#!/usr/bin/env python3
"""
plot_results.py — turns results/bench.csv into comparison charts, one per
metric, grouped by filter and distribution. Saves PNGs into results/.

Usage: python3 scripts/plot_results.py [path/to/bench.csv]
"""
import sys
import os
import csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

CSV_PATH = sys.argv[1] if len(sys.argv) > 1 else "results/bench.csv"
OUT_DIR = os.path.dirname(CSV_PATH) or "."

FILTER_ORDER = ["bloom", "cuckoo", "cqf"]
DIST_ORDER = ["uniform", "zipfian"]
COLORS = {"bloom": "#4C72B0", "cuckoo": "#DD8452", "cqf": "#55A868"}


def load_rows(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def grouped_bar(rows, value_key, title, ylabel, fname, log_scale=False):
    fig, axes = plt.subplots(1, len(DIST_ORDER), figsize=(10, 4.5), sharey=not log_scale)
    if len(DIST_ORDER) == 1:
        axes = [axes]

    for ax, dist in zip(axes, DIST_ORDER):
        vals, colors, labels = [], [], []
        for filt in FILTER_ORDER:
            match = [r for r in rows if r["filter"] == filt and r["distribution"] == dist]
            if not match:
                continue
            v = float(match[0][value_key])
            vals.append(v)
            colors.append(COLORS[filt])
            labels.append(filt)
        bars = ax.bar(labels, vals, color=colors)
        ax.set_title(dist)
        ax.set_ylabel(ylabel)
        if log_scale:
            ax.set_yscale("log")
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:,.3g}",
                     ha="center", va="bottom", fontsize=8)

    fig.suptitle(title)
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, fname)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def fp_comparison(rows, fname):
    fig, axes = plt.subplots(1, len(DIST_ORDER), figsize=(10, 4.5))
    if len(DIST_ORDER) == 1:
        axes = [axes]

    width = 0.35
    for ax, dist in zip(axes, DIST_ORDER):
        filters, measured, theoretical = [], [], []
        for filt in FILTER_ORDER:
            match = [r for r in rows if r["filter"] == filt and r["distribution"] == dist]
            if not match:
                continue
            filters.append(filt)
            measured.append(float(match[0]["measured_fp_rate"]))
            theoretical.append(float(match[0]["theoretical_fp_rate"]))
        x = range(len(filters))
        ax.bar([i - width / 2 for i in x], measured, width, label="measured", color="#4C72B0")
        ax.bar([i + width / 2 for i in x], theoretical, width, label="theoretical", color="#C44E52")
        ax.set_xticks(list(x))
        ax.set_xticklabels(filters)
        ax.set_title(dist)
        ax.set_ylabel("false-positive rate")
        ax.legend(fontsize=8)

    fig.suptitle("Measured vs. theoretical false-positive rate")
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, fname)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def main():
    if not os.path.exists(CSV_PATH):
        print(f"No results file at {CSV_PATH}. Run scripts/run_all.sh first.")
        sys.exit(1)

    rows = load_rows(CSV_PATH)
    if not rows:
        print("bench.csv is empty.")
        sys.exit(1)

    grouped_bar(rows, "insert_ops_sec", "Insert throughput", "ops/sec", "chart_insert_throughput.png")
    grouped_bar(rows, "query_pos_ops_sec", "Positive-lookup throughput", "ops/sec", "chart_query_throughput.png")
    grouped_bar(rows, "memory_bytes", "Memory usage", "bytes", "chart_memory.png", log_scale=True)
    fp_comparison(rows, "chart_false_positive_rate.png")

    print("\nAll charts written to", OUT_DIR)


if __name__ == "__main__":
    main()
