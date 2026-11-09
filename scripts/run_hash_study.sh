#!/usr/bin/env bash
# Controlled CQF hash-mode comparison.
# Usage: run_hash_study.sh [N] [NEG] [UNIVERSE] [SKEW] [REPEATS] [OUTPUT_TAG] [full|skip-delete]
# An optional tag keeps additional scales separate (e.g. output tag 67m).
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-1000000}
NEG=${2:-10000000}
UNIVERSE=${3:-201000000}
SKEW=${4:-1.5}
REPEATS=${5:-3}
OUTPUT_TAG=${6:-}
DELETE_MODE=${7:-full}
if [[ "$DELETE_MODE" != "full" && "$DELETE_MODE" != "skip-delete" ]]; then
  echo "DELETE_MODE must be full or skip-delete" >&2; exit 1
fi
if (( N <= 0 || NEG <= 0 || REPEATS <= 0 )); then
  echo "N, NEG and REPEATS must be positive" >&2; exit 1
fi
if [[ -n "$OUTPUT_TAG" && ! "$OUTPUT_TAG" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "OUTPUT_TAG may contain only letters, digits and underscores" >&2; exit 1
fi
if [[ -n "$OUTPUT_TAG" ]]; then
  STEM="hash_modes_${OUTPUT_TAG}"
  DATA="results/extended/hash_data_${OUTPUT_TAG}"
else
  STEM="hash_modes"
  DATA="results/extended/hash_data"
fi
OUT="results/extended/${STEM}_raw.csv"
AGG="results/extended/${STEM}.csv"
CFG="results/extended/${STEM}_configuration.txt"
mkdir -p results/extended
rm -f "$OUT" "$AGG"
./scripts/build_all.sh
# Reuse a matching generated workload. Regenerating a 67M binary input can
# take several minutes and is not needed for repeat timing runs.
if [[ ! -f "$DATA/manifest.txt" ]] || \
   ! grep -qx "n=$N" "$DATA/manifest.txt" || \
   ! grep -qx "universe=$UNIVERSE" "$DATA/manifest.txt" || \
   ! grep -qx "skew=$SKEW" "$DATA/manifest.txt" || \
   ! grep -qx "neg=$NEG" "$DATA/manifest.txt" || \
   ! grep -qx "seed=42" "$DATA/manifest.txt" || \
   [[ ! -s "$DATA/uniform_positive.bin" || ! -s "$DATA/uniform_negative.bin" || \
      ! -s "$DATA/zipf_positive.bin" || ! -s "$DATA/zipf_negative.bin" ]]; then
  rm -rf "$DATA"
  python3 data/generate_data.py --outdir "$DATA" --n "$N" --universe "$UNIVERSE" --skew "$SKEW" --neg "$NEG" --seed 42 --binary
else
  echo "Reusing matching generated workload: $DATA"
fi
UNIFORM_DISTINCT=$(awk -F= '$1=="uniform_distinct_keys"{print $2}' "$DATA/manifest.txt")
ZIPF_DISTINCT=$(awk -F= '$1=="zipf_distinct_keys"{print $2}' "$DATA/manifest.txt")
# Use the smallest power-of-two table that leaves at least 5% headroom.
read -r QBITS < <(python3 - "$N" <<'PY'
import math,sys
n=int(sys.argv[1]); print(max(10, math.ceil(math.log2((n-1)/0.95))))
PY
)
RBITS=9
cat > "$CFG" <<CFG
requested_operations=$N
negative_queries=$NEG
uniform_distinct_keys=$UNIFORM_DISTINCT
zipf_distinct_keys=$ZIPF_DISTINCT
zipf_universe=$UNIVERSE
zipf_skew=$SKEW
seed=42
cqf_qbits=$QBITS
cqf_slots=$((1 << QBITS))
cqf_rbits=$RBITS
repeats=$REPEATS
hash_modes=default,invertible,none
delete_mode=$DELETE_MODE
CFG
for dist in uniform zipfian; do
  if [[ "$dist" == uniform ]]; then pos="$DATA/uniform_positive.bin"; neg="$DATA/uniform_negative.bin"; distinct="$UNIFORM_DISTINCT";
  else pos="$DATA/zipf_positive.bin"; neg="$DATA/zipf_negative.bin"; distinct="$ZIPF_DISTINCT"; fi
  for mode in default invertible none; do
    for repeat in $(seq 1 "$REPEATS"); do
      echo "CQF hash mode=$mode workload=$dist repeat=$repeat/$REPEATS N=$N"
      if [[ "$DELETE_MODE" == "skip-delete" ]]; then
        ./cqf/bench_cqf "$pos" "$neg" "$QBITS" "$RBITS" "$dist" "$OUT" "$mode" "$distinct" skip-delete
      else
        ./cqf/bench_cqf "$pos" "$neg" "$QBITS" "$RBITS" "$dist" "$OUT" "$mode" "$distinct"
      fi
    done
  done
done
python3 scripts/aggregate_results.py "$OUT" "$AGG"
python3 scripts/plot_hash_modes.py "$OUTPUT_TAG"
python3 - "$AGG" "$N" "$DELETE_MODE" <<'PY'
import csv,sys
rows=list(csv.DictReader(open(sys.argv[1])))
n=int(sys.argv[2]); delete_mode=sys.argv[3]
assert len(rows)==6, f'expected 6 aggregate rows, got {len(rows)}'
for r in rows:
    assert int(r['n_requested']) == n, r
    assert int(r['found_positive']) == int(r['n_inserted']), r
    if delete_mode == "full":
        assert int(r['deleted_ok']) == int(r['n_inserted']), r
    else:
        assert r['deleted_ok'] == "NA", r
    assert int(r['n_inserted']) == n, r
print('Hash-mode insertion/lookup checks passed; deletion mode:', delete_mode)
PY
printf 'CSV: %s\nRaw: %s\nConfiguration: %s\n' "$AGG" "$OUT" "$CFG"
