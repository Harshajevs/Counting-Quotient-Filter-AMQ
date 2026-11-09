#!/usr/bin/env bash
# Run 67M paper-scale data at three target FPRs.
# Usage: run_fpr_sweep.sh [N] [NEG] [OTHER_REPEATS] [PRIMARY_1_512_REPEATS]
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-67000000}
NEG=${2:-10000000}
OTHER_REPEATS=${3:-1}
PRIMARY_REPEATS=${4:-3}
for target in 1/256 1/512 1/1024; do
  repeats=$OTHER_REPEATS
  [[ "$target" == "1/512" ]] && repeats=$PRIMARY_REPEATS
  ./scripts/run_paper_scale.sh "$N" "$NEG" "$target" "$repeats"
done
python3 scripts/plot_fpr_sweep.py
