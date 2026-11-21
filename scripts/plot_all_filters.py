#!/usr/bin/env python3
"""Generate consistent plots from the unified all-filters table."""
import csv
import sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

if len(sys.argv) != 3:
    raise SystemExit("Usage: plot_all_filters.py ALL_FILTERS.csv OUTPUT_PREFIX")
source, prefix = sys.argv[1:]
with open(source, newline="") as f:
    rows = list(csv.DictReader(f))
if not rows:
    raise SystemExit("No rows to plot")

filters = []
for r in rows:
    if r["filter"] not in filters: filters.append(r["filter"])
dists = ["uniform", "zipfian"]


def val(r, key):
    # Do not compare the partial Cuckoo structure after an early capacity
    # failure as if it represented the complete Zipfian key set. Its allocated
    # memory is still a valid configuration measurement.
    if r.get("result_status") == "capacity_failure" and key != "memory_bytes":
        return np.nan
    try:
        x = float(r.get(key, "NA"))
        return x if np.isfinite(x) else np.nan
    except (TypeError, ValueError):
        return np.nan


def grouped_plot(metric, title, ylabel, suffix, static_separate=False, log=False):
    use_filters = filters
    fig, ax = plt.subplots(figsize=(max(10, len(use_filters)*1.15), 6))
    width = 0.36
    x = np.arange(len(use_filters))
    for j, dist in enumerate(dists):
        y=[]
        for name in use_filters:
            match=[r for r in rows if r["filter"]==name and r["distribution"]==dist]
            y.append(val(match[0],metric) if match else np.nan)
        ax.bar(x+(j-0.5)*width, y, width, label=dist.capitalize())
    ax.set_xticks(x); ax.set_xticklabels(use_filters, rotation=20, ha="right")
    ax.set_title(title); ax.set_ylabel(ylabel); ax.grid(axis="y", alpha=.25); ax.legend()
    if log: ax.set_yscale("log")
    fig.tight_layout(); fig.savefig(f"{prefix}_{suffix}.png", dpi=180); plt.close(fig)

# Dynamic insertion and static construction are separated because their
# operation contracts differ. Static filters cannot accept per-key inserts.
fig, axes = plt.subplots(1,2,figsize=(14,5.5))
for ax, cls, metric, ttl in [
    (axes[0],"dynamic","insert_ops_sec","Online insertion throughput (dynamic filters)"),
    (axes[1],"static","build_ops_sec","Static construction throughput (build once)"),
]:
    names=[n for n in filters if any(r["filter"]==n and r["filter_class"]==cls for r in rows)]
    x=np.arange(len(names)); width=.36
    for j,dist in enumerate(dists):
        ys=[]
        for name in names:
            m=[r for r in rows if r["filter"]==name and r["distribution"]==dist]
            ys.append(val(m[0],metric) if m else np.nan)
        ax.bar(x+(j-.5)*width,ys,width,label=dist.capitalize())
    ax.set_xticks(x); ax.set_xticklabels(names,rotation=20,ha="right")
    ax.set_title(ttl)
    ax.set_ylabel("Insertions / second" if cls == "dynamic" else "Distinct keys built / second")
    ax.grid(axis="y",alpha=.25)
    if j==1: ax.legend()
axes[0].legend(); fig.tight_layout(); fig.savefig(f"{prefix}_insert_build.png",dpi=180); plt.close(fig)

grouped_plot("query_pos_ops_sec","Positive membership lookup throughput","Queries / second","positive_lookup")
grouped_plot("query_neg_ops_sec","Negative membership lookup throughput","Queries / second","negative_lookup")
grouped_plot("memory_bytes","Final filter footprint","Bytes","memory")
grouped_plot("measured_fp_rate","Measured false-positive rate","False-positive rate","fpr",log=True)

fig, ax = plt.subplots(figsize=(10,5.5))
active=[n for n in filters if any(r["filter"]==n and r["delete_supported"]=="yes" for r in rows)]
x=np.arange(len(active)); width=.36
for j,dist in enumerate(dists):
    ys=[]
    for name in active:
        m=[r for r in rows if r["filter"]==name and r["distribution"]==dist]
        ys.append(val(m[0],"delete_ops_sec") if m else np.nan)
    ax.bar(x+(j-.5)*width,ys,width,label=dist.capitalize())
ax.set_xticks(x);ax.set_xticklabels(active,rotation=20,ha="right")
ax.set_title("Deletion throughput (supported dynamic filters only)");ax.set_ylabel("Deletes / second")
ax.grid(axis="y",alpha=.25);ax.legend();fig.tight_layout();fig.savefig(f"{prefix}_delete.png",dpi=180);plt.close(fig)

# Average per-operation latency is derived as elapsed batch time / operation
# count. It is mean ns/op, not a per-operation timestamp or percentile.
fig, axes = plt.subplots(1, 2, figsize=(14, 5.5))
for ax, cls, metric, ttl in [
    (axes[0], "dynamic", "insert_ns_per_operation", "Online insertion latency (dynamic filters)"),
    (axes[1], "static", "end_to_end_build_ns_per_input_operation", "Static end-to-end build latency / input operation"),
]:
    names=[n for n in filters if any(r["filter"]==n and r["filter_class"]==cls for r in rows)]
    x=np.arange(len(names)); width=.36
    for j,dist in enumerate(dists):
        ys=[]
        for name in names:
            m=[r for r in rows if r["filter"]==name and r["distribution"]==dist]
            ys.append(val(m[0],metric) if m else np.nan)
        ax.bar(x+(j-.5)*width,ys,width,label=dist.capitalize())
    ax.set_xticks(x);ax.set_xticklabels(names,rotation=20,ha="right")
    ax.set_title(ttl);ax.set_ylabel("Nanoseconds per input operation")
    ax.grid(axis="y",alpha=.25);ax.legend()
fig.tight_layout();fig.savefig(f"{prefix}_insert_build_latency.png",dpi=180);plt.close(fig)

grouped_plot("positive_lookup_ns_per_query", "Positive lookup average latency", "Nanoseconds / query", "positive_lookup_latency")
grouped_plot("negative_lookup_ns_per_query", "Negative lookup average latency", "Nanoseconds / query", "negative_lookup_latency")

fig, ax = plt.subplots(figsize=(10,5.5))
active=[n for n in filters if any(r["filter"]==n and r["delete_supported"]=="yes" for r in rows)]
x=np.arange(len(active));width=.36
for j,dist in enumerate(dists):
    ys=[]
    for name in active:
        m=[r for r in rows if r["filter"]==name and r["distribution"]==dist]
        ys.append(val(m[0],"delete_ns_per_operation") if m else np.nan)
    ax.bar(x+(j-.5)*width,ys,width,label=dist.capitalize())
ax.set_xticks(x);ax.set_xticklabels(active,rotation=20,ha="right")
ax.set_title("Deletion average latency (supported filters only)")
ax.set_ylabel("Nanoseconds / delete operation");ax.grid(axis="y",alpha=.25);ax.legend()
fig.tight_layout();fig.savefig(f"{prefix}_delete_latency.png",dpi=180);plt.close(fig)

print(f"Unified comparison plots written with prefix {prefix}")
