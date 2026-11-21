#!/usr/bin/env bash
# Run one common workload through the original filters and all newly added filters.
# Usage: run_filter_expansion.sh [N] [NEG] [TARGET_FPR] [REPEATS] [TAG]
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-1000000}
NEG=${2:-1000000}
TARGET=${3:-1/512}
REPEATS=${4:-3}
TAG=${5:-expanded_1_512}
if [[ ! "$TAG" =~ ^[A-Za-z0-9_]+$ ]]; then echo "TAG may contain only letters, digits and underscores" >&2; exit 1; fi
if (( N <= 0 || NEG <= 0 || REPEATS <= 0 )); then echo "N, NEG and REPEATS must be positive" >&2; exit 1; fi

# The original three filters create/reuse the shared 64-bit binary workloads
# and produce the legacy-compatible CQF/Cuckoo/Bloom comparison.
./scripts/run_paper_scale.sh "$N" "$NEG" "$TARGET" "$REPEATS" "$TAG"

DATA=results/extended/paper_scale_data
RAW="results/extended/additional_filters_${TAG}_raw.csv"
AGG="results/extended/additional_filters_${TAG}.csv"
ALL="results/extended/all_filters_${TAG}.csv"
rm -f "$RAW" "$AGG" "$ALL"

python3 - "$TARGET" <<'PY'
import sys
raw=sys.argv[1]
p=float(raw.split('/')[0])/float(raw.split('/')[1]) if '/' in raw else float(raw)
if not 0<p<1: raise SystemExit('TARGET_FPR must be in (0,1)')
print(f'Additional filters target FPR: {p:.12g}')
PY

for dist in uniform zipfian; do
  if [[ "$dist" == uniform ]]; then
    POS="$DATA/uniform_positive.bin"; NEG_FILE="$DATA/uniform_negative.bin"
  else
    POS="$DATA/zipf_positive.bin"; NEG_FILE="$DATA/zipf_negative.bin"
  fi
  for rep in $(seq 1 "$REPEATS"); do
    echo "== Added filters: $dist repeat $rep/$REPEATS target=$TARGET =="
    ./filters/bench_extra_filters "$POS" "$NEG_FILE" \
      "$(python3 - "$TARGET" <<'PY'
import sys
s=sys.argv[1]
print(float(s.split('/')[0])/float(s.split('/')[1]) if '/' in s else float(s))
PY
)" "$dist" "$RAW" "$rep"
  done
done

python3 scripts/aggregate_extra_filters.py "$RAW" "$AGG"
python3 scripts/merge_all_filters.py \
  "results/extended/paper_scale_${TAG}.csv" "$AGG" \
  "$DATA/manifest.txt" "$NEG" "$ALL"
python3 scripts/plot_all_filters.py "$ALL" "results/extended/all_filters_${TAG}"
python3 scripts/verify_all_filters.py "$TAG" "$REPEATS"

echo
echo "== Unified AMQ comparison completed =="
echo "Base filters : results/extended/paper_scale_${TAG}.csv"
echo "Added raw    : $RAW"
echo "Added mean   : $AGG"
echo "All filters  : $ALL"
echo "Plots        : results/extended/all_filters_${TAG}_*.png"
