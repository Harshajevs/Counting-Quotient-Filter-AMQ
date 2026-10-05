#!/usr/bin/env bash
# test_all.sh — build and run lightweight functional regression tests.
set -euo pipefail
cd "$(dirname "$0")/.."

./scripts/build_all.sh >/dev/null

echo "== CQF counting/deletion regression test =="
gcc -std=gnu11 -Wall -O2 -msse4.2 -mpopcnt -mbmi -mbmi2 \
    -Icqf/include \
    tests/test_cqf_counting.c \
    cqf/src/gqf.c cqf/src/hashutil.c cqf/src/partitioned_counter.c \
    -o /tmp/test_cqf_counting -lpthread -lssl -lcrypto -lm
/tmp/test_cqf_counting
rm -f /tmp/test_cqf_counting

echo "== Data-generator regression test =="
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
python3 data/generate_data.py --outdir "$TMP_DIR" --n 10000 --universe 201000000 --skew 1.5 --neg 5000 --seed 42 >/dev/null
python3 - "$TMP_DIR" <<'PY'
from pathlib import Path
import sys

root = Path(sys.argv[1])
positive = set()
with (root / "zipf_positive.txt").open() as f:
    for line in f:
        positive.add(int(line))

negative = [int(x) for x in (root / "zipf_negative.txt").read_text().splitlines()]
assert len(negative) == 5000
assert not any(x in positive for x in negative)
assert len(positive) > 1
print("[test_data_generator] PASS")
PY

echo "All functional regression tests passed."
