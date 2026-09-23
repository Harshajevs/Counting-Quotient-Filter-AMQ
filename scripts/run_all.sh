#!/usr/bin/env bash
# run_all.sh — generates the shared datasets and runs all three filters
# through them, producing one combined results/bench.csv.
#
# Usage: ./scripts/run_all.sh [N] [UNIVERSE] [SKEW] [NEG]
#   N        = number of positive (inserted) keys        (default 1,000,000)
#   UNIVERSE = distinct-item universe for the Zipfian set (default 200,000)
#   SKEW     = Zipfian skew parameter s                   (default 1.5, matches the paper)
#   NEG      = number of negative keys for FP testing     (default 100,000)
set -e
cd "$(dirname "$0")/.."

N=${1:-1000000}
UNIVERSE=${2:-200000}
SKEW=${3:-1.5}
NEG=${4:-100000}
SEED=42

DATA_DIR=results/data
OUT_CSV=results/bench.csv

echo "== Step 1/3: generating shared datasets =="
python3 data/generate_data.py --outdir "$DATA_DIR" \
    --n "$N" --universe "$UNIVERSE" --skew "$SKEW" --neg "$NEG" --seed "$SEED"

echo "== Step 2/3: building benchmark binaries =="
./scripts/build_all.sh

echo "== Step 3/3: running benchmarks =="
rm -f "$OUT_CSV"

# --- CQF: qbits chosen so 2^qbits is comfortably above N (roughly 90% target load factor) ---
QBITS=$(python3 -c "import math; print(max(10, math.ceil(math.log2($N / 0.9))))")
RBITS=9   # theoretical FP = 2^-9 ~= 0.00195, close to the cuckoo/bloom configs below

echo "--- CQF (qbits=$QBITS rbits=$RBITS) ---"
./cqf/bench_cqf "$DATA_DIR/uniform_positive.txt" "$DATA_DIR/uniform_negative.txt" "$QBITS" "$RBITS" uniform "$OUT_CSV"
./cqf/bench_cqf "$DATA_DIR/zipf_positive.txt"    "$DATA_DIR/zipf_negative.txt"    "$QBITS" "$RBITS" zipfian "$OUT_CSV"

# --- Cuckoo filter: bits_per_item=12 is the closest supported size to CQF's 9-bit remainder ---
echo "--- Cuckoo filter (bits_per_item=12) ---"
./cuckoo/bench_cuckoo "$DATA_DIR/uniform_positive.txt" "$DATA_DIR/uniform_negative.txt" "$N" 12 uniform "$OUT_CSV"
./cuckoo/bench_cuckoo "$DATA_DIR/zipf_positive.txt"    "$DATA_DIR/zipf_negative.txt"    "$N" 12 zipfian "$OUT_CSV"

# --- Bloom filter: size in bits chosen for ~1/512 target FP rate at load N (same target as the paper) ---
SIZE_BITS=$(python3 -c "import math; n=$N; fp=1/512; k=4; print(math.ceil(-k*n/math.log(1-fp**(1/k))))")
echo "--- Bloom filter (size_bits=$SIZE_BITS, k=4) ---"
./bloom/bench_bloom "$DATA_DIR/uniform_positive.txt" "$DATA_DIR/uniform_negative.txt" "$SIZE_BITS" 4 uniform "$OUT_CSV"
./bloom/bench_bloom "$DATA_DIR/zipf_positive.txt"    "$DATA_DIR/zipf_negative.txt"    "$SIZE_BITS" 4 zipfian "$OUT_CSV"

echo
echo "== Done. Results written to $OUT_CSV =="
echo "Run 'python3 scripts/plot_results.py' to generate comparison charts."
