#!/usr/bin/env bash
# Paper-scale comparison at a selectable target FPR.
# Usage: run_paper_scale.sh [N] [NEG] [TARGET_FPR] [REPEATS] [OUTPUT_TAG]
# TARGET_FPR accepts 1/256, 1/512, 1/1024 or a decimal probability.
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-67000000}
NEG=${2:-10000000}
TARGET_FP=${3:-1/512}
REPEATS=${4:-1}
UNIVERSE=201000000
SKEW=1.5
SEED=42

if (( N <= 0 || NEG <= 0 || REPEATS <= 0 )); then
  echo "N, NEG and REPEATS must be positive" >&2; exit 1
fi

read -r P QBITS SLOTS RBITS CUCKOO_BITS BLOOM_BITS BLOOM_K TAG < <(
python3 - "$N" "$TARGET_FP" <<'PY'
import math,sys
n=int(sys.argv[1]); raw=sys.argv[2]
try:
    if '/' in raw:
        a,b=raw.split('/',1); p=float(a)/float(b)
    else: p=float(raw)
except ValueError: raise SystemExit('TARGET_FPR must be a fraction such as 1/512 or a decimal')
if not (0 < p < 1): raise SystemExit('TARGET_FPR must lie strictly between 0 and 1')
q=max(10,math.ceil(math.log2(n/0.95)))
slots=1<<q
r=max(1,math.ceil(-math.log2(p)))
# The imported Cuckoo implementation is validated only for 8/12/16-bit tags.
# Choose the smallest supported tag width whose nominal FPR is <= target.
f=next((bits for bits in (8,12,16) if 8/(2**bits) <= p),16)
bpe=-math.log(p)/(math.log(2)**2)
k=max(1,round(bpe*math.log(2)))
m=math.ceil(-k*n/math.log(1-p**(1.0/k)))
tag=raw.replace('/','_').replace('.','p')
print(f'{p:.12g}',q,slots,r,f,m,k,tag)
PY
)

OUTPUT_TAG=${5:-$TAG}
if [[ ! "$OUTPUT_TAG" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "OUTPUT_TAG may contain only letters, digits and underscores" >&2; exit 1
fi
TAG=$OUTPUT_TAG
DATA=results/extended/paper_scale_data
RAW=results/extended/paper_scale_${TAG}_raw.csv
AGG=results/extended/paper_scale_${TAG}.csv
mkdir -p results/extended
rm -f "$RAW" "$AGG"
./scripts/build_all.sh
if [[ ! -f "$DATA/manifest.txt" ]] || ! grep -qx "n=$N" "$DATA/manifest.txt" || ! grep -qx "neg=$NEG" "$DATA/manifest.txt"; then
  rm -rf "$DATA"
  python3 data/generate_data.py --outdir "$DATA" --n "$N" --universe "$UNIVERSE" --skew "$SKEW" --neg "$NEG" --seed "$SEED" --binary
fi
UNIFORM_DISTINCT=$(awk -F= '$1=="uniform_distinct_keys"{print $2}' "$DATA/manifest.txt")
ZIPF_DISTINCT=$(awk -F= '$1=="zipf_distinct_keys"{print $2}' "$DATA/manifest.txt")

cat > "results/extended/paper_scale_${TAG}_configuration.txt" <<CFG
requested_operations=$N
negative_queries=$NEG
uniform_distinct_keys=$UNIFORM_DISTINCT
zipf_distinct_keys=$ZIPF_DISTINCT
zipf_universe=$UNIVERSE
zipf_skew=$SKEW
target_fpr=$TARGET_FP
cqf_qbits=$QBITS
cqf_slots=$SLOTS
cqf_rbits=$RBITS
cqf_uniform_distinct_load=$(python3 - "$UNIFORM_DISTINCT" "$SLOTS" <<'PY'
import sys; print(f'{int(sys.argv[1])/int(sys.argv[2]):.8f}')
PY
)
cqf_zipf_distinct_load=$(python3 - "$ZIPF_DISTINCT" "$SLOTS" <<'PY'
import sys; print(f'{int(sys.argv[1])/int(sys.argv[2]):.8f}')
PY
)
cuckoo_fingerprint_bits=$CUCKOO_BITS
bloom_bits=$BLOOM_BITS
bloom_hash_functions=$BLOOM_K
repeats=$REPEATS
CFG

for dist in uniform zipfian; do
  if [[ "$dist" == uniform ]]; then pos="$DATA/uniform_positive.bin"; neg="$DATA/uniform_negative.bin"; distinct="$UNIFORM_DISTINCT";
  else pos="$DATA/zipf_positive.bin"; neg="$DATA/zipf_negative.bin"; distinct="$ZIPF_DISTINCT"; fi
  for repeat in $(seq 1 "$REPEATS"); do
    echo "== Paper-scale $dist repeat $repeat/$REPEATS target=$TARGET_FP =="
    ./cqf/bench_cqf "$pos" "$neg" "$QBITS" "$RBITS" "$dist" "$RAW" default "$distinct"
    ./cuckoo/bench_cuckoo "$pos" "$neg" "$N" "$CUCKOO_BITS" "$dist" "$RAW"
    ./bloom/bench_bloom "$pos" "$neg" "$BLOOM_BITS" "$BLOOM_K" "$dist" "$RAW" "$distinct"
  done
done
python3 scripts/aggregate_results.py "$RAW" "$AGG"
python3 - "$AGG" "$N" "$REPEATS" <<'PY'
import csv,sys
path,n,reps=sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
rows=list(csv.DictReader(open(path)))
assert len(rows)==6, f'expected 6 rows, got {len(rows)}'
for r in rows:
    assert int(r['found_positive']) == int(r['n_inserted']), r
    if r['filter'] in ('cqf','bloom') or (r['filter']=='cuckoo' and r['distribution']=='uniform'):
        assert int(r['n_inserted'])==n, r
    if r['filter']!='bloom': assert int(r['deleted_ok'])==int(r['n_inserted']),r
print('Paper-scale output validation passed (6 rows, positive lookups, deletes, and complete insertions where expected).')
PY
python3 scripts/plot_extended.py "paper_scale_${TAG}"
echo "CSV: $AGG"
echo "Raw: $RAW"
echo "Configuration: results/extended/paper_scale_${TAG}_configuration.txt"
