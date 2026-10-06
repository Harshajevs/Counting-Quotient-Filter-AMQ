#!/usr/bin/env python3
"""
plot_results.py — turns results/bench.csv into comparison charts, one per
metric, grouped by filter and distribution, plus a combined dashboard.
Saves PNGs into results/.

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


def get(rows, filt, dist, key):
    match = [r for r in rows if r["filter"] == filt and r["distribution"] == dist]
    return float(match[0][key]) if match else None


def grouped_bar(rows, value_key, title, ylabel, fname, log_scale=False, note_zero_as=None):
    fig, axes = plt.subplots(1, len(DIST_ORDER), figsize=(10, 4.5), sharey=not log_scale)
    if len(DIST_ORDER) == 1:
        axes = [axes]

    for ax, dist in zip(axes, DIST_ORDER):
        vals, colors, labels = [], [], []
        for filt in FILTER_ORDER:
            v = get(rows, filt, dist, value_key)
            if v is None:
                continue
            vals.append(v)
            colors.append(COLORS[filt])
            labels.append(filt)
        bars = ax.bar(labels, vals, color=colors)
        ax.set_title(dist)
        ax.set_ylabel(ylabel)
        if log_scale:
            ax.set_yscale("log")
        for b, v, lab in zip(bars, vals, labels):
            text = note_zero_as if (v == 0 and note_zero_as) else f"{v:,.3g}"
            ax.text(b.get_x() + b.get_width() / 2, max(v, (ax.get_ylim()[1] * 1e-6)),
                    text, ha="center", va="bottom", fontsize=8)

    fig.suptitle(title)
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, fname)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def _zipf_distinct_keys(csv_path):
    """Return the number of distinct Zipf keys for the current benchmark.

    Normal benchmark runs write this value to data/manifest.txt.  The
    checked-in results archive does not include generated data, so fall back
    to the distinct-key count used to produce its current Zipf results.
    """
    project_root = os.path.abspath(os.path.join(os.path.dirname(csv_path), os.pardir))
    manifest_path = os.path.join(project_root, "data", "manifest.txt")
    try:
        with open(manifest_path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("zipf_distinct_keys="):
                    return int(line.split("=", 1)[1].strip())
    except (OSError, ValueError):
        pass
    return 14_061


def _theoretical_bloom_fp(config_param, n_distinct):
    """Bloom FPR for the actual number of distinct inserted keys."""
    parts = {}
    for item in config_param.split(";"):
        if "=" in item:
            key, value = item.split("=", 1)
            parts[key] = value
    try:
        m = int(parts["size_bits"])
        k = int(parts["k"])
    except (KeyError, ValueError):
        return None
    return (1.0 - pow(2.718281828459045, -(k * n_distinct) / m)) ** k


def fp_comparison(rows, fname):
    fig, axes = plt.subplots(1, len(DIST_ORDER), figsize=(10, 4.5))
    if len(DIST_ORDER) == 1:
        axes = [axes]

    width = 0.35
    zipf_distinct = _zipf_distinct_keys(CSV_PATH)
    for ax, dist in zip(axes, DIST_ORDER):
        filters, measured, theoretical = [], [], []
        for filt in FILTER_ORDER:
            m = get(rows, filt, dist, "measured_fp_rate")
            t = get(rows, filt, dist, "theoretical_fp_rate")
            if m is None:
                continue

            # For the duplicate-heavy Zipfian workload, the nominal 1/512
            # target is not the workload-specific Bloom FPR: Bloom sees only
            # the distinct inserted keys.  Cuckoo accepted only 24 inserts
            # before failing, so a normal theoretical-FPR comparison is not
            # meaningful for that run.  Leave the other graphs/results alone.
            if dist == "zipfian" and filt == "bloom":
                row = next(r for r in rows
                           if r["filter"] == filt and r["distribution"] == dist)
                t = _theoretical_bloom_fp(row["config_param"], zipf_distinct)
            elif dist == "zipfian" and filt == "cuckoo":
                t = None

            filters.append(filt)
            measured.append(m)
            theoretical.append(t)

        x = list(range(len(filters)))
        ax.bar([i - width / 2 for i in x], measured, width, label="measured", color="#4C72B0")

        theoretical_x = [i + width / 2 for i, t in enumerate(theoretical) if t is not None]
        theoretical_y = [t for t in theoretical if t is not None]
        if theoretical_y:
            ax.bar(theoretical_x, theoretical_y, width, label="theoretical", color="#C44E52")

        # Make the failed Zipfian Cuckoo comparison explicit without drawing
        # a misleading theoretical bar.
        if dist == "zipfian" and "cuckoo" in filters:
            i = filters.index("cuckoo")
            ax.text(i + width / 2, 0.00182, "N/A",
                    ha="center", va="bottom", fontsize=8)

        ax.set_xticks(x)
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


def fp_ratio_chart(rows, fname):
    """measured/theoretical ratio -- 1.0 means a perfect match to theory,
    >1 means worse than theory, <1 means better than theory (safe side)."""
    fig, axes = plt.subplots(1, len(DIST_ORDER), figsize=(10, 4.5), sharey=True)
    if len(DIST_ORDER) == 1:
        axes = [axes]

    for ax, dist in zip(axes, DIST_ORDER):
        vals, colors, labels = [], [], []
        for filt in FILTER_ORDER:
            v = get(rows, filt, dist, "fp_ratio")
            if v is None:
                continue
            vals.append(v)
            colors.append(COLORS[filt])
            labels.append(filt)
        bars = ax.bar(labels, vals, color=colors)
        ax.axhline(1.0, color="black", linestyle="--", linewidth=1, label="theoretical (=1.0)")
        ax.set_title(dist)
        ax.set_ylabel("measured / theoretical FP rate")
        ax.legend(fontsize=8)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.2f}x", ha="center", va="bottom", fontsize=8)

    fig.suptitle("False-positive ratio (1.0 = exactly matches theory)")
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, fname)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def capacity_chart(rows, fname):
    """Compare requested and accepted insert operations.

    This makes a capacity/failure event visible without implying that every
    accepted operation corresponds to a distinct key (Zipfian inputs contain
    duplicates).
    """
    fig, axes = plt.subplots(1, len(DIST_ORDER), figsize=(10, 4.5), sharey=True)
    if len(DIST_ORDER) == 1:
        axes = [axes]

    width = 0.35
    for ax, dist in zip(axes, DIST_ORDER):
        filters, requested, inserted = [], [], []
        for filt in FILTER_ORDER:
            r = get(rows, filt, dist, "n_requested")
            ins = get(rows, filt, dist, "n_inserted")
            if r is None:
                continue
            filters.append(filt)
            requested.append(r)
            inserted.append(ins)
        x = range(len(filters))
        ax.bar([i - width / 2 for i in x], requested, width, label="requested", color="#8C8C8C")
        ax.bar([i + width / 2 for i in x], inserted, width, label="actually inserted", color="#55A868")
        ax.set_xticks(list(x))
        ax.set_xticklabels(filters)
        ax.set_title(dist)
        ax.set_ylabel("number of keys")
        ax.legend(fontsize=8)
        for i, (r, ins) in enumerate(zip(requested, inserted)):
            if ins < r:
                ax.annotate(f"only {ins:,.0f}\naccepted!", xy=(i + width / 2, ins),
                            xytext=(i + width / 2, r * 0.5),
                            ha="center", fontsize=8, color="#C44E52",
                            arrowprops=dict(arrowstyle="->", color="#C44E52"))

    fig.suptitle("Requested vs. accepted insert operations (capacity/failure)")
    fig.tight_layout()
    out_path = os.path.join(OUT_DIR, fname)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"wrote {out_path}")


def dashboard(rows, fname):
    """One combined figure with every metric, for a quick-glance slide."""
    metrics = [
        ("insert_ops_sec", "Insert throughput (ops/sec)", True),
        ("query_pos_ops_sec", "Positive-lookup throughput (ops/sec)", True),
        ("query_neg_ops_sec", "Negative-lookup throughput (ops/sec)", True),
        ("delete_ops_sec", "Delete throughput (ops/sec)", True),
        ("memory_bytes", "Memory usage (bytes)", True),
        ("fp_ratio", "FP ratio (measured/theoretical)", False),
    ]
    fig, axes = plt.subplots(2, 6, figsize=(22, 7))
    for col, (key, title, log_scale) in enumerate(metrics):
        for row, dist in enumerate(DIST_ORDER):
            ax = axes[row][col]
            vals, colors, labels = [], [], []
            for filt in FILTER_ORDER:
                v = get(rows, filt, dist, key)
                if v is None:
                    continue
                vals.append(v)
                colors.append(COLORS[filt])
                labels.append(filt)
            ax.bar(labels, vals, color=colors)
            if log_scale:
                ax.set_yscale("log")
            if row == 0:
                ax.set_title(title, fontsize=9)
            if col == 0:
                ax.set_ylabel(dist, fontsize=10)
            ax.tick_params(axis="both", labelsize=7)

    fig.suptitle("AMQ benchmark dashboard: Bloom vs. cuckoo vs. CQF", fontsize=14)
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
    grouped_bar(rows, "query_neg_ops_sec", "Negative-lookup throughput", "ops/sec", "chart_query_neg_throughput.png")
    grouped_bar(rows, "delete_ops_sec", "Delete throughput", "ops/sec", "chart_delete_throughput.png",
                note_zero_as="not\nsupported")
    grouped_bar(rows, "memory_bytes", "Memory usage", "bytes", "chart_memory.png", log_scale=True)
    fp_comparison(rows, "chart_false_positive_rate.png")
    fp_ratio_chart(rows, "chart_fp_ratio.png")
    capacity_chart(rows, "chart_capacity.png")
    dashboard(rows, "chart_dashboard.png")

    print("\nAll charts written to", OUT_DIR)


if __name__ == "__main__":
    main()
