#!/usr/bin/env bash
# Run the 7-filter comparison at three target false-positive rates.
# Usage: run_filter_expansion_sweep.sh [N] [NEG] [REPEATS] [TAG_PREFIX]
set -euo pipefail
cd "$(dirname "$0")/.."
N=${1:-1000000}
NEG=${2:-1000000}
REPEATS=${3:-3}
PREFIX=${4:-expanded}
if [[ ! "$PREFIX" =~ ^[A-Za-z0-9_]+$ ]]; then
  echo "TAG_PREFIX may contain only letters, digits and underscores" >&2; exit 1
fi
for target in 1/256 1/512 1/1024; do
  suffix=${target//\//_}
  echo
  echo "============================================================"
  echo "Unified 7-filter experiment: N=$N NEG=$NEG target=$target repeats=$REPEATS"
  echo "============================================================"
  ./scripts/run_filter_expansion.sh "$N" "$NEG" "$target" "$REPEATS" "${PREFIX}_${suffix}"
done

echo
echo "All target-FPR comparisons completed."
