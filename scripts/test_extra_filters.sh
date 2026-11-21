#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
g++ -std=c++17 -Wall -Wextra -O2 -march=x86-64-v2 -Ifilters \
  tests/test_additional_filters.cpp -o /tmp/test_additional_filters
/tmp/test_additional_filters
rm -f /tmp/test_additional_filters
