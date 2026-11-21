#!/usr/bin/env bash
# Paper-scale comparison at a selectable target FPR.
# Usage: run_paper_scale.sh [N] [NEG] [TARGET_FPR] [REPEATS] [OUTPUT_TAG]
# CQF and Cuckoo are sized from requested insertion operations; Bloom is
# sized from exact distinct cardinality. Every requested operation is replayed.
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

read -r P RBITS CUCKOO_BITS TAG < <(
python3 - "$N" "$TARGET_FP" <<'PY2'
import math,sys
n=int(sys.argv[1]); raw=sys.argv[2]
try:
    if '/' in raw:
        a,b=raw.split('/',1); p=float(a)/float(b)
    else: p=float(raw)
except ValueError: raise SystemExit('TARGET_FPR must be a fraction such as 1/512 or a decimal')
if not (0 < p < 1): raise SystemExit('TARGET_FPR must lie strictly between 0 and 1')
r=max(1,math.ceil(-math.log2(p)))
# Imported Cuckoo baseline supports 8, 12 and 16-bit fingerprints.
f=next((bits for bits in (8,12,16) if 8/(2**bits) <= p),16)
tag=raw.replace('/','_').replace('.','p')
print(f'{p:.12g}',r,f,tag)
PY2
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
# Exact verification is excluded from every timed filter phase.
python3 scripts/audit_workloads.py "$DATA"
UNIFORM_DISTINCT=$(awk -F= '$1=="uniform_distinct_keys"{print $2}' "$DATA/manifest.txt")
ZIPF_DISTINCT=$(awk -F= '$1=="zipf_distinct_keys"{print $2}' "$DATA/manifest.txt")

filter_params() {
  python3 - "$N" "$2" "$P" <<'PY2'
import math,sys
operation_count=int(sys.argv[1]); membership_count=max(1,int(sys.argv[2])); p=float(sys.argv[3])
# CQF needs room for its counter encoding as well as distinct runs, so its
# table remains sized from the full operation count in this implementation.
q=max(10,math.ceil(math.log2(operation_count/0.95)))
slots=1<<q
r=max(1,math.ceil(-math.log2(p)))
# Bloom is a set-membership structure: repeated keys do not consume new bits.
bpe=-math.log(p)/(math.log(2)**2)
k=max(1,round(bpe*math.log(2)))
m=math.ceil(-k*membership_count/math.log(1-p**(1.0/k)))
print(q,slots,r,m,k)
PY2
}
read -r U_QBITS U_SLOTS U_RBITS U_BLOOM_BITS U_BLOOM_K < <(filter_params "$N" "$UNIFORM_DISTINCT")
read -r Z_QBITS Z_SLOTS Z_RBITS Z_BLOOM_BITS Z_BLOOM_K < <(filter_params "$N" "$ZIPF_DISTINCT")

cat > "results/extended/paper_scale_${TAG}_configuration.txt" <<CFG
requested_operations=$N
negative_queries=$NEG
uniform_distinct_keys=$UNIFORM_DISTINCT
zipf_distinct_keys=$ZIPF_DISTINCT
zipf_universe=$UNIVERSE
zipf_skew=$SKEW
target_fpr=$TARGET_FP
cqf_and_cuckoo_capacity_basis=requested_operations
bloom_and_static_set_capacity_basis=distinct_keys_per_workload
counting_and_blocked_bloom_capacity_basis=distinct_keys_per_workload
uniform_cqf_qbits=$U_QBITS
uniform_cqf_slots=$U_SLOTS
uniform_cqf_rbits=$U_RBITS
uniform_cqf_distinct_load=$(python3 - "$UNIFORM_DISTINCT" "$U_SLOTS" <<'PY2'
import sys; print(f'{int(sys.argv[1])/int(sys.argv[2]):.8f}')
PY2
)
zipf_cqf_qbits=$Z_QBITS
zipf_cqf_slots=$Z_SLOTS
zipf_cqf_rbits=$Z_RBITS
zipf_cqf_distinct_load=$(python3 - "$ZIPF_DISTINCT" "$Z_SLOTS" <<'PY2'
import sys; print(f'{int(sys.argv[1])/int(sys.argv[2]):.8f}')
PY2
)
cuckoo_fingerprint_bits=$CUCKOO_BITS
uniform_bloom_bits=$U_BLOOM_BITS
uniform_bloom_hash_functions=$U_BLOOM_K
zipf_bloom_bits=$Z_BLOOM_BITS
zipf_bloom_hash_functions=$Z_BLOOM_K
repeats=$REPEATS
CFG

for dist in uniform zipfian; do
  if [[ "$dist" == "uniform" ]]; then
    pos="$DATA/uniform_positive.bin"; neg="$DATA/uniform_negative.bin"; distinct="$UNIFORM_DISTINCT"
    qbits=$U_QBITS; slots=$U_SLOTS; rbits=$U_RBITS; bloom_bits=$U_BLOOM_BITS; bloom_k=$U_BLOOM_K
  else
    pos="$DATA/zipf_positive.bin"; neg="$DATA/zipf_negative.bin"; distinct="$ZIPF_DISTINCT"
    qbits=$Z_QBITS; slots=$Z_SLOTS; rbits=$Z_RBITS; bloom_bits=$Z_BLOOM_BITS; bloom_k=$Z_BLOOM_K
  fi
  echo "== $dist capacity: distinct=$distinct; CQF qbits=$qbits slots=$slots; Bloom m=$bloom_bits k=$bloom_k =="
  for repeat in $(seq 1 "$REPEATS"); do
    echo "== Paper-scale $dist repeat $repeat/$REPEATS target=$TARGET_FP =="
    ./cqf/bench_cqf "$pos" "$neg" "$qbits" "$rbits" "$dist" "$RAW" default "$distinct"
    ./cuckoo/bench_cuckoo "$pos" "$neg" "$N" "$CUCKOO_BITS" "$dist" "$RAW"
    ./bloom/bench_bloom "$pos" "$neg" "$bloom_bits" "$bloom_k" "$dist" "$RAW" "$distinct"
  done
done
python3 scripts/aggregate_results.py "$RAW" "$AGG"
python3 - "$AGG" "$N" "$REPEATS" <<'PY2'
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
PY2
python3 scripts/plot_extended.py "paper_scale_${TAG}"
echo "CSV: $AGG"
echo "Raw: $RAW"
echo "Configuration: results/extended/paper_scale_${TAG}_configuration.txt"
