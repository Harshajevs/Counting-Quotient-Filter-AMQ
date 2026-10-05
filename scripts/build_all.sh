#!/usr/bin/env bash
# build_all.sh — compile the three benchmark drivers on Linux/x86_64.
# CQF uses a runtime-selected BMI2/TZCNT rank-select fast path when available,
# with a portable fallback in the same binary.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "== Building CQF benchmark =="
gcc -std=gnu11 -Wall -Wextra -O3 -msse4.2 -mpopcnt -mbmi -mbmi2 -m64 \
    -Icqf -Icqf/include \
    cqf/bench_cqf.c cqf/src/gqf.c cqf/src/hashutil.c cqf/src/partitioned_counter.c \
    -o cqf/bench_cqf -lpthread -lssl -lcrypto -lm

echo "== Building Cuckoo filter benchmark =="
g++ -std=c++11 -fno-strict-aliasing -Wall -Wextra -O3 -march=x86-64-v2 \
    -Icuckoo -Icuckoo/src \
    cuckoo/bench_cuckoo.cc cuckoo/src/hashutil.cc \
    -lpthread -lssl -lcrypto -o cuckoo/bench_cuckoo

echo "== Building Bloom filter benchmark =="
g++ -std=c++11 -Wall -Wextra -O3 -march=x86-64-v2 \
    bloom/bench_bloom.cc -o bloom/bench_bloom -lm

echo "== Build complete =="
echo "  cqf/bench_cqf"
echo "  cuckoo/bench_cuckoo"
echo "  bloom/bench_bloom"
