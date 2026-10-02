#!/usr/bin/env bash
# build_all.sh — compiles all three benchmark drivers.
# Run this from the repo root: ./scripts/build_all.sh
set -e
cd "$(dirname "$0")/.."

echo "== Building CQF benchmark =="
gcc -std=gnu11 -Wall -Ofast -msse4.2 -D__SSE4_2_ -m64 -Icqf -Icqf/include \
    cqf/bench_cqf.c cqf/src/gqf.c cqf/src/hashutil.c cqf/src/partitioned_counter.c \
    -o cqf/bench_cqf -lpthread -lssl -lcrypto -lm

echo "== Building cuckoo filter benchmark =="
g++ --std=c++11 -fno-strict-aliasing -Wall -O2 -Icuckoo -Icuckoo/src \
    cuckoo/bench_cuckoo.cc cuckoo/src/hashutil.cc \
    -lpthread -lssl -lcrypto -o cuckoo/bench_cuckoo

echo "== Building Bloom filter benchmark =="
g++ --std=c++11 -Wall -O2 bloom/bench_bloom.cc -o bloom/bench_bloom -lm

echo "== Build complete =="
echo "  cqf/bench_cqf"
echo "  cuckoo/bench_cuckoo"
echo "  bloom/bench_bloom"
