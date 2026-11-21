#!/usr/bin/env python3
"""Aggregate raw added-filter runs by filter and distribution."""
import csv
import statistics
import sys
from collections import defaultdict

if len(sys.argv) != 3:
    raise SystemExit("Usage: aggregate_extra_filters.py RAW.csv AGG.csv")
raw_path, out_path = sys.argv[1:]
with open(raw_path, newline="") as f:
    rows = list(csv.DictReader(f))
if not rows:
    raise SystemExit(f"No rows in {raw_path}")
groups = defaultdict(list)
for row in rows:
    groups[(row["filter"], row["distribution"])].append(row)

non_numeric = {"filter", "filter_class", "operation_model", "distribution", "repeat_id", "config_param",
               "insert_supported", "delete_supported"}
fields = list(rows[0].keys())
out_rows = []
for key, group in sorted(groups.items()):
    out = {}
    for field in fields:
        vals = [r[field] for r in group]
        if field in non_numeric:
            out[field] = vals[0] if field != "repeat_id" else f"mean_of_{len(group)}"
            continue
        numeric = []
        for v in vals:
            try:
                numeric.append(float(v))
            except (TypeError, ValueError):
                pass
        if not numeric:
            out[field] = "NA"
        elif field in {"n_requested", "n_distinct", "n_inserted", "memory_bytes", "query_pos_count",
                       "found_positive", "query_neg_count", "false_positives", "deleted_ok", "auxiliary_bytes"}:
            out[field] = str(int(round(statistics.mean(numeric))))
        else:
            out[field] = f"{statistics.mean(numeric):.12g}"
    out_rows.append(out)
with open(out_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(out_rows)
print(f"Aggregated {len(rows)} raw rows into {len(out_rows)} rows: {out_path}")
