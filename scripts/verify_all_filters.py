#!/usr/bin/env python3
"""Sanity-check the unified comparison and explicitly modeled operation support."""
import csv
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("Usage: verify_all_filters.py TAG REPEATS")
tag, repeats = sys.argv[1], int(sys.argv[2])
root = Path("results/extended")

def read(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

base = read(root / f"paper_scale_{tag}.csv")
raw = read(root / f"additional_filters_{tag}_raw.csv")
extra = read(root / f"additional_filters_{tag}.csv")
all_rows = read(root / f"all_filters_{tag}.csv")
assert len(base) == 6, f"expected 6 baseline rows, got {len(base)}"
assert len(raw) == 8 * repeats, f"expected {8*repeats} added raw rows, got {len(raw)}"
assert len(extra) == 8, f"expected 8 aggregate added rows, got {len(extra)}"
assert len(all_rows) == 14, f"expected 14 unified rows, got {len(all_rows)}"

for r in raw + extra + all_rows:
    assert int(r["n_requested"]) > 0
    assert int(r["found_positive"]) == int(r["query_pos_count"]), f"positive lookup mismatch: {r}"
    if r.get("result_status") != "capacity_failure":
        for metric in ("positive_lookup_ns_per_query", "negative_lookup_ns_per_query"):
            if metric in r:
                assert float(r[metric]) > 0, f"missing/invalid derived latency {metric}: {r}"
    assert int(r["memory_bytes"]) > 0, f"missing memory accounting: {r}"
    if r.get("result_status") == "capacity_failure" and r.get("measured_fp_rate") == "NA":
        pass
    else:
        p = float(r["measured_fp_rate"])
        assert 0.0 <= p <= 1.0, f"invalid measured FPR: {r}"

for r in extra:
    if r["filter"] in {"blocked_bloom", "counting_bloom"}:
        assert r["filter_class"] == "dynamic" and r["insert_supported"] == "yes"
        assert int(r["n_inserted"]) == int(r["n_requested"])
    if r["filter"] == "counting_bloom":
        assert r["delete_supported"] == "yes"
        assert int(r["deleted_ok"]) == int(r["n_requested"])
    if r["filter"] == "blocked_bloom":
        assert r["delete_supported"] == "no" and r["deleted_ok"] == "NA"
    if r["filter"] in {"xor", "binary_fuse"}:
        assert r["filter_class"] == "static" and r["insert_supported"] == "no"
        assert r["delete_supported"] == "no"
        assert r["build_time_s"] != "NA"
        assert int(r["n_inserted"]) == int(r["n_distinct"])
        assert r["deleted_ok"] == "NA"

for r in all_rows:
    if r["filter"] in {"xor", "binary_fuse"}:
        assert r["result_status"] == "static_immutable"
        assert float(r["end_to_end_build_ns_per_distinct_key"]) > 0
    if r["filter"] == "cuckoo" and r["distribution"] == "zipfian" and int(r["n_inserted"]) < int(r["n_requested"]):
        assert r["result_status"] == "capacity_failure"
        assert r["measured_fp_rate"] == "NA" and r["theoretical_fp_rate"] == "NA"
        assert r["insert_ops_sec"] == "NA" and r["delete_ops_sec"] == "NA"
        assert r["query_pos_ops_sec"] == "NA" and r["query_neg_ops_sec"] == "NA"
        assert r["positive_lookup_ns_per_query"] == "NA"
        assert r["negative_lookup_ns_per_query"] == "NA"

for name in [
    f"all_filters_{tag}_insert_build.png",
    f"all_filters_{tag}_positive_lookup.png",
    f"all_filters_{tag}_negative_lookup.png",
    f"all_filters_{tag}_delete.png",
    f"all_filters_{tag}_memory.png",
    f"all_filters_{tag}_fpr.png",
    f"all_filters_{tag}_insert_build_latency.png",
    f"all_filters_{tag}_positive_lookup_latency.png",
    f"all_filters_{tag}_negative_lookup_latency.png",
    f"all_filters_{tag}_delete_latency.png",
]:
    p = root / name
    assert p.exists() and p.stat().st_size > 0, f"missing or empty plot: {p}"

print("PASS: 6 original + 4 added filter families (8 distribution rows)")
print(f"PASS: {len(raw)} added raw repetitions, {len(extra)} aggregated rows")
print("PASS: positive lookups, explicit operation support/failures, memory, FPR, latency and plots")
print("ALL UNIFIED FILTER CHECKS PASSED.")
