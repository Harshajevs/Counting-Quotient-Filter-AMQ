#!/usr/bin/env python3
"""Merge the legacy CQF/Cuckoo/Bloom rows with the new common-schema rows."""
import csv
import sys
from pathlib import Path

if len(sys.argv) != 6:
    raise SystemExit("Usage: merge_all_filters.py BASE.csv EXTRA.csv MANIFEST.txt NEG_COUNT OUT.csv")
base_path, extra_path, manifest_path, neg_arg, out_path = sys.argv[1:]
neg_count = int(neg_arg)
manifest = {}
for line in Path(manifest_path).read_text().splitlines():
    if "=" in line:
        k, v = line.split("=", 1)
        manifest[k] = v

fields = ["filter", "filter_class", "operation_model", "result_status", "distribution", "repeat_id", "n_requested",
          "n_distinct", "n_inserted", "config_param", "memory_bytes", "preprocess_time_s", "build_time_s",
          "build_ops_sec", "insert_supported", "insert_time_s", "insert_ops_sec", "query_pos_count",
          "query_pos_time_s", "query_pos_ops_sec", "found_positive", "query_neg_count", "query_neg_time_s",
          "query_neg_ops_sec", "false_positives", "measured_fp_rate", "theoretical_fp_rate", "fp_ratio",
          "delete_supported", "delete_time_s", "delete_ops_sec", "deleted_ok", "auxiliary_bytes",
          "preprocess_ns_per_distinct_key", "preprocess_ns_per_input_operation",
          "static_build_ns_per_distinct_key", "end_to_end_build_ns_per_distinct_key",
          "end_to_end_build_ns_per_input_operation", "end_to_end_build_ops_sec", "insert_ns_per_operation",
          "positive_lookup_ns_per_query", "negative_lookup_ns_per_query",
          "delete_ns_per_operation"]

with open(base_path, newline="") as f:
    base_rows = list(csv.DictReader(f))
with open(extra_path, newline="") as f:
    extra_rows = list(csv.DictReader(f))

def ns_per_op(time_value, count_value):
    try:
        t=float(time_value); n=float(count_value)
        if t <= 0 or n <= 0: return "NA"
        return f"{t * 1e9 / n:.6f}"
    except (TypeError, ValueError):
        return "NA"

merged = []
for r in base_rows:
    dist = r["distribution"]
    distinct = manifest.get("uniform_distinct_keys" if dist == "uniform" else "zipf_distinct_keys", r["n_inserted"])
    n_inserted = r["n_inserted"]
    row = {
        "filter": r["filter"], "filter_class": "dynamic",
        "operation_model": "online_insert_no_delete" if r["filter"] == "bloom" else "online_insert_delete",
        "result_status": "complete", "distribution": dist, "repeat_id": "aggregate",
        "n_requested": r["n_requested"], "n_distinct": distinct, "n_inserted": n_inserted,
        "config_param": r["config_param"], "memory_bytes": r["memory_bytes"],
        "preprocess_time_s": "NA", "build_time_s": "NA", "build_ops_sec": "NA",
        "insert_supported": "yes", "insert_time_s": r["insert_time_s"], "insert_ops_sec": r["insert_ops_sec"],
        "query_pos_count": n_inserted, "query_pos_time_s": r["query_pos_time_s"],
        "query_pos_ops_sec": r["query_pos_ops_sec"], "found_positive": r["found_positive"],
        "query_neg_count": neg_count, "query_neg_time_s": r["query_neg_time_s"],
        "query_neg_ops_sec": r["query_neg_ops_sec"], "false_positives": "NA",
        "measured_fp_rate": r["measured_fp_rate"], "theoretical_fp_rate": r["theoretical_fp_rate"],
        "fp_ratio": r["fp_ratio"], "delete_supported": "no" if r["filter"] == "bloom" else "yes",
        "delete_time_s": r["delete_time_s"], "delete_ops_sec": r["delete_ops_sec"],
        "deleted_ok": r["deleted_ok"], "auxiliary_bytes": 0,
        "preprocess_ns_per_distinct_key": "NA", "preprocess_ns_per_input_operation": "NA",
        "static_build_ns_per_distinct_key": "NA", "end_to_end_build_ns_per_distinct_key": "NA",
        "end_to_end_build_ns_per_input_operation": "NA", "end_to_end_build_ops_sec": "NA",
        "insert_ns_per_operation": ns_per_op(r["insert_time_s"], r["n_requested"]),
        "positive_lookup_ns_per_query": ns_per_op(r["query_pos_time_s"], n_inserted),
        "negative_lookup_ns_per_query": ns_per_op(r["query_neg_time_s"], neg_count),
        "delete_ns_per_operation": ns_per_op(r["delete_time_s"], r["deleted_ok"]),
    }
    if row["delete_supported"] == "no":
        row["delete_time_s"] = row["delete_ops_sec"] = row["deleted_ok"] = "NA"
    # The Cuckoo/Zipf row is a failed/partial construction and its FPR is not
    # a meaningful steady-state operating point.
    if r["filter"] == "cuckoo" and dist == "zipfian" and int(n_inserted) < int(r["n_requested"]):
        row["result_status"] = "capacity_failure"
        row["operation_model"] = "online_insert_capacity_failure"
        row["insert_supported"] = "partial"
        row["insert_ops_sec"] = "NA"
        row["insert_ns_per_operation"] = "NA"
        row["positive_lookup_ns_per_query"] = "NA" if row["positive_lookup_ns_per_query"] == "0.000000" else row["positive_lookup_ns_per_query"]
        row["measured_fp_rate"] = row["theoretical_fp_rate"] = row["fp_ratio"] = "NA"
        # The filter contains only a tiny accepted subset, so its lookup
        # rates are not comparable with filters that accepted the full set.
        # Keep the query counts/found count as diagnostics, but suppress
        # timings and derived rates in the unified comparison.
        row["query_pos_time_s"] = row["query_pos_ops_sec"] = "NA"
        row["query_neg_time_s"] = row["query_neg_ops_sec"] = "NA"
        row["positive_lookup_ns_per_query"] = "NA"
        row["negative_lookup_ns_per_query"] = "NA"
        row["delete_supported"] = "partial"
        row["delete_time_s"] = row["delete_ops_sec"] = row["deleted_ok"] = "NA"
        row["delete_ns_per_operation"] = "NA"
    merged.append(row)

for r in extra_rows:
    row={k: r.get(k, "NA") for k in fields}
    row["result_status"] = "static_immutable" if r.get("filter_class") == "static" else "complete"
    row["preprocess_ns_per_distinct_key"] = ns_per_op(r.get("preprocess_time_s", "NA"), r.get("n_distinct", "NA"))
    row["preprocess_ns_per_input_operation"] = ns_per_op(r.get("preprocess_time_s", "NA"), r.get("n_requested", "NA"))
    row["static_build_ns_per_distinct_key"] = ns_per_op(r.get("build_time_s", "NA"), r.get("n_distinct", "NA"))
    try:
        total_build=float(r.get("preprocess_time_s", "NA"))+float(r.get("build_time_s", "NA"))
        row["end_to_end_build_ns_per_distinct_key"] = ns_per_op(total_build, r.get("n_distinct", "NA"))
        row["end_to_end_build_ns_per_input_operation"] = ns_per_op(total_build, r.get("n_requested", "NA"))
        row["end_to_end_build_ops_sec"] = f"{int(r.get('n_requested', 0))/total_build:.6f}" if total_build > 0 else "NA"
    except (TypeError, ValueError, ZeroDivisionError):
        row["end_to_end_build_ns_per_distinct_key"] = "NA"
        row["end_to_end_build_ns_per_input_operation"] = "NA"
        row["end_to_end_build_ops_sec"] = "NA"
    row["insert_ns_per_operation"] = ns_per_op(r.get("insert_time_s", "NA"), r.get("n_requested", "NA"))
    row["positive_lookup_ns_per_query"] = ns_per_op(r.get("query_pos_time_s", "NA"), r.get("query_pos_count", "NA"))
    row["negative_lookup_ns_per_query"] = ns_per_op(r.get("query_neg_time_s", "NA"), r.get("query_neg_count", "NA"))
    row["delete_ns_per_operation"] = ns_per_op(r.get("delete_time_s", "NA"), r.get("deleted_ok", "NA"))
    merged.append(row)

with open(out_path, "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(merged)
print(f"Merged {len(base_rows)} existing + {len(extra_rows)} new filter rows -> {out_path}")
