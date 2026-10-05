#!/usr/bin/env python3
"""
aggregate_results.py — averages multiple repeated benchmark runs into one
stable bench.csv. Timing/throughput numbers can be noisy on a single run
(background load, scheduler jitter, etc.), so run_all.sh runs each
filter/distribution combination several times and this script averages the
numeric columns, grouped by (filter, distribution, config_param).

Count-based columns (n_inserted, found_positive, deleted_ok, memory_bytes)
should be identical across repeats of the same deterministic input, so this
also sanity-checks that and warns if they're not.

Usage: python3 scripts/aggregate_results.py results/bench_raw.csv results/bench.csv
"""
import sys
import csv
from collections import defaultdict

NUMERIC_AVG_COLS = [
    "insert_time_s", "insert_ops_sec",
    "query_pos_time_s", "query_pos_ops_sec",
    "query_neg_time_s", "query_neg_ops_sec",
    "measured_fp_rate", "theoretical_fp_rate", "fp_ratio",
    "delete_time_s", "delete_ops_sec",
]
STABLE_COLS = ["n_requested", "n_inserted", "memory_bytes", "found_positive", "deleted_ok"]
KEY_COLS = ["filter", "distribution", "config_param"]


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else "results/bench_raw.csv"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "results/bench.csv"

    with open(in_path) as f:
        rows = list(csv.DictReader(f))

    groups = defaultdict(list)
    for r in rows:
        key = tuple(r[c] for c in KEY_COLS)
        groups[key].append(r)

    # Keep the public CSV column order identical to the benchmark drivers.
    fieldnames = [
        "filter", "distribution", "n_requested", "n_inserted", "config_param",
        "memory_bytes", "insert_time_s", "insert_ops_sec",
        "query_pos_time_s", "query_pos_ops_sec", "found_positive",
        "query_neg_time_s", "query_neg_ops_sec", "measured_fp_rate",
        "theoretical_fp_rate", "fp_ratio", "delete_time_s", "delete_ops_sec",
        "deleted_ok",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for key, group_rows in groups.items():
            out = dict(zip(KEY_COLS, key))

            for c in STABLE_COLS:
                vals = set(r[c] for r in group_rows)
                if len(vals) > 1:
                    print(f"WARNING: {key} column '{c}' differs across repeats: {vals} "
                          f"(using the first value; this shouldn't happen for deterministic input)")
                out[c] = group_rows[0][c]

            for c in NUMERIC_AVG_COLS:
                vals = [float(r[c]) for r in group_rows]
                value = sum(vals) / len(vals)
                # Keep the same human-readable precision as the individual
                # benchmark drivers while retaining enough detail for analysis.
                if c.endswith("_time_s"):
                    out[c] = f"{value:.9f}"
                elif c.endswith("_ops_sec"):
                    out[c] = f"{value:.2f}"
                elif c in ("measured_fp_rate", "theoretical_fp_rate"):
                    out[c] = f"{value:.8f}"
                elif c == "fp_ratio":
                    out[c] = f"{value:.4f}"
                else:
                    out[c] = f"{value:.6f}"

            w.writerow(out)
            n = len(group_rows)
            print(f"{key[0]:8s} {key[1]:8s}  averaged over {n} run(s)")

    print(f"\nWrote aggregated results to {out_path}")


if __name__ == "__main__":
    main()
