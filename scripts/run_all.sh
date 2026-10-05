#!/usr/bin/env bash
# run_all.sh — generate one shared workload and benchmark Bloom, Cuckoo, and CQF.
#
# The sizing is deliberately tied to the paper's 1/512 target and ~95% CQF/Cuckoo
# load factor.  For N=1,000,000 the smallest power-of-two CQF table is 2^20,
# whose 95% usable point is 996,148 insertions.  We therefore benchmark exactly
# that many operations for every filter so the comparisons use the same input
# prefix and the same number of operations.
#
# Usage:
#   ./scripts/run_all.sh [N] [UNIVERSE] [SKEW] [NEG] [REPEATS]
#
# Defaults:
#   N=1,000,000, UNIVERSE=201,000,000, SKEW=1.5, NEG=100,000, REPEATS=3
set -euo pipefail
cd "$(dirname "$0")/.."

TARGET_N=${1:-1000000}
UNIVERSE=${2:-201000000}
SKEW=${3:-1.5}
NEG=${4:-100000}
REPEATS=${5:-3}
SEED=42

if (( TARGET_N <= 0 || NEG <= 0 || REPEATS <= 0 )); then
    echo "N, NEG and REPEATS must be positive" >&2
    exit 1
fi

DATA_DIR=results/data
RAW_CSV=results/bench_raw.csv
OUT_CSV=results/bench.csv

# Smallest power-of-two CQF table that can contain TARGET_N at all.
read -r QBITS CQF_SLOTS CQF_SAFE_N EVAL_N < <(
python3 - "$TARGET_N" <<'PY'
import math
import sys
N = int(sys.argv[1])
qbits = max(10, math.ceil(math.log2(N)))
slots = 1 << qbits
# qf_insert's fullness guard fires before inserting once occupied >= 0.95*slots.
# With the reference implementation's integer slot count, this means that the
# largest accepted count is ceil(0.95*slots) for the workloads we use here.
safe_n = math.ceil(0.95 * slots)
eval_n = min(N, safe_n)
print(qbits, slots, safe_n, eval_n)
PY
)

RBITS=9
TARGET_FP=0.001953125

# Bloom target follows the paper: smallest practical space at the requested FPR,
# with the optimal integer number of hash functions.
read -r BLOOM_BITS BLOOM_K < <(
python3 - "$EVAL_N" "$TARGET_FP" <<'PY'
import math
import sys
n = int(sys.argv[1])
p = float(sys.argv[2])
# Continuous optimum: m/n = -ln(p)/(ln 2)^2, k = (m/n) ln 2.
bpe = -math.log(p) / (math.log(2) ** 2)
k = max(1, int(round(bpe * math.log(2))))
# Use the exact m needed by that integer k to hit the configured target.
m = math.ceil(-k * n / math.log(1 - p ** (1.0 / k)))
print(m, k)
PY
)

CUCKOO_BITS=12

rm -rf "$DATA_DIR"
mkdir -p "$DATA_DIR" results
rm -f "$RAW_CSV" "$OUT_CSV"

cat <<INFO
== AMQ benchmark configuration ==
requested target N : $TARGET_N
benchmark N        : $EVAL_N
CQF qbits          : $QBITS ($CQF_SLOTS slots)
CQF usable point   : $CQF_SAFE_N (~95% occupancy)
CQF rbits          : $RBITS (FPR bound 1/512)
Cuckoo fingerprint : $CUCKOO_BITS bits (4-way buckets)
Bloom size         : $BLOOM_BITS bits (~$(( (BLOOM_BITS + 7) / 8 )) bytes)
Bloom hashes       : $BLOOM_K (near-optimal for 1/512)
Zipf universe      : $UNIVERSE
Zipf skew          : $SKEW
Negative queries   : $NEG
Repeats            : $REPEATS
INFO

echo "== Step 1/4: generating shared datasets =="
python3 data/generate_data.py --outdir "$DATA_DIR" \
    --n "$EVAL_N" --universe "$UNIVERSE" --skew "$SKEW" \
    --neg "$NEG" --seed "$SEED"

echo "== Step 2/4: building benchmark binaries =="
./scripts/build_all.sh

echo "== Step 3/4: running benchmarks ($REPEATS repeat(s) each) =="

for i in $(seq 1 "$REPEATS"); do
    echo "--- repeat $i/$REPEATS ---"

    echo "  CQF (qbits=$QBITS rbits=$RBITS)"
    ./cqf/bench_cqf \
        "$DATA_DIR/uniform_positive.txt" "$DATA_DIR/uniform_negative.txt" \
        "$QBITS" "$RBITS" uniform "$RAW_CSV"
    ./cqf/bench_cqf \
        "$DATA_DIR/zipf_positive.txt" "$DATA_DIR/zipf_negative.txt" \
        "$QBITS" "$RBITS" zipfian "$RAW_CSV"

    echo "  Cuckoo filter (capacity=$EVAL_N bits_per_item=$CUCKOO_BITS)"
    ./cuckoo/bench_cuckoo \
        "$DATA_DIR/uniform_positive.txt" "$DATA_DIR/uniform_negative.txt" \
        "$EVAL_N" "$CUCKOO_BITS" uniform "$RAW_CSV"
    ./cuckoo/bench_cuckoo \
        "$DATA_DIR/zipf_positive.txt" "$DATA_DIR/zipf_negative.txt" \
        "$EVAL_N" "$CUCKOO_BITS" zipfian "$RAW_CSV"

    echo "  Bloom filter (size_bits=$BLOOM_BITS k=$BLOOM_K)"
    ./bloom/bench_bloom \
        "$DATA_DIR/uniform_positive.txt" "$DATA_DIR/uniform_negative.txt" \
        "$BLOOM_BITS" "$BLOOM_K" uniform "$RAW_CSV"
    ./bloom/bench_bloom \
        "$DATA_DIR/zipf_positive.txt" "$DATA_DIR/zipf_negative.txt" \
        "$BLOOM_BITS" "$BLOOM_K" zipfian "$RAW_CSV"
done

echo "== Step 4/4: aggregating repeats into $OUT_CSV =="
python3 scripts/aggregate_results.py "$RAW_CSV" "$OUT_CSV"

python3 - "$RAW_CSV" "$OUT_CSV" "$REPEATS" "$EVAL_N" <<'PY'
import csv
import sys
raw, agg, expected_repeats, expected_n = sys.argv[1:]
expected_repeats = int(expected_repeats)
expected_n = int(expected_n)
with open(raw, newline='') as f:
    raw_rows = list(csv.DictReader(f))
with open(agg, newline='') as f:
    agg_rows = list(csv.DictReader(f))
print(f"raw rows: {len(raw_rows)}")
print(f"aggregate rows: {len(agg_rows)}")
if len(raw_rows) != expected_repeats * 6 or len(agg_rows) != 6:
    raise SystemExit("Result-shape validation failed")
for r in raw_rows:
    inserted = int(r['n_inserted'])
    requested = int(r['n_requested'])
    found = int(r['found_positive'])
    deleted = int(r['deleted_ok'])

    if found != inserted:
        raise SystemExit(f"Positive lookup validation failed: {r}")

    # These are the configurations expected to process the full common
    # workload.  Cuckoo/Zipfian is intentionally allowed to fail early; that
    # failure is one of the paper's key skewed-workload observations.
    if r['filter'] == 'cqf' and inserted != expected_n:
        raise SystemExit(f"CQF insertion failure: inserted={inserted}, expected={expected_n}: {r}")
    if r['filter'] == 'bloom' and inserted != expected_n:
        raise SystemExit(f"Bloom insertion failure: inserted={inserted}, expected={expected_n}: {r}")
    if r['filter'] == 'cuckoo' and r['distribution'] == 'uniform' and inserted != expected_n:
        raise SystemExit(f"Uniform Cuckoo insertion failure: inserted={inserted}, expected={expected_n}: {r}")

    if r['filter'] != 'bloom' and deleted != inserted:
        raise SystemExit(f"Delete validation failed: {r}")

print("Result-shape and functional sanity checks passed.")
PY

echo
echo "== Done =="
echo "Raw runs : $RAW_CSV"
echo "Average  : $OUT_CSV"
echo "Charts   : run 'python3 scripts/plot_results.py'"
