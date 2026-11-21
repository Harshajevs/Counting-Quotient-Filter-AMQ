#!/usr/bin/env bash
# Reproduce the experiments used in the November 2026 research report.
# Run in the supported linux/amd64 environment from this repository root.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p results/report
rm -f results/report/COMPLETED.txt results/report/compact_zipf_raw.csv results/report/geometry_control_raw.csv
{
  date -u +%FT%TZ
  uname -a
  cat /etc/os-release
  gcc --version | head -1
  g++ --version | head -1
  python3 -c 'import numpy,pandas,matplotlib; print("NumPy",numpy.__version__,"pandas",pandas.__version__,"matplotlib",matplotlib.__version__)'
  head -n 30 /proc/cpuinfo
  head -n 4 /proc/meminfo
} > results/report/environment.txt
./scripts/test_all.sh > results/report/tests.log 2>&1
./scripts/run_filter_expansion.sh 1000000 10000000 1/512 3 report_1m > results/report/run_1m.log 2>&1
cp results/extended/paper_scale_data/manifest.txt results/report/manifest_1m.txt
cp results/extended/paper_scale_data/audit.json results/report/audit_1m.json
./scripts/run_hash_study.sh 996148 10000000 201000000 1.5 3 report_control > results/report/hash_control.log 2>&1
./scripts/run_filter_expansion.sh 67000000 10000000 1/512 3 report_67m > results/report/run_67m.log 2>&1
cp results/extended/paper_scale_data/manifest.txt results/report/manifest_67m.txt
cp results/extended/paper_scale_data/audit.json results/report/audit_67m.json
# Reuse identical 67M inputs without a second multi-gigabyte data directory.
ln -sfn paper_scale_data results/extended/hash_data_report_67m
./scripts/run_hash_study.sh 67000000 10000000 201000000 1.5 3 report_67m skip-delete > results/report/hash_67m.log 2>&1
./scripts/run_filter_expansion.sh 67000000 10000000 1/256 1 report_67m_256 > results/report/run_67m_256.log 2>&1
./scripts/run_filter_expansion.sh 67000000 10000000 1/1024 1 report_67m_1024 > results/report/run_67m_1024.log 2>&1
# A separately labelled CQF compact-capacity sensitivity experiment on the
# same Zipf stream; it does not replace the operation-sized primary CQF.
./cqf/bench_cqf results/extended/paper_scale_data/zipf_positive.bin \
  results/extended/paper_scale_data/zipf_negative.bin 19 9 zipfian \
  results/report/compact_zipf_raw.csv default "$(awk -F= '$1=="zipf_distinct_keys"{print $2}' results/extended/paper_scale_data/manifest.txt)" > results/report/compact_zipf.log 2>&1
# Matched-N geometry sensitivity: q changes; r=9, hence p=q+r also changes.
./scripts/run_paper_scale.sh 63753420 10000000 1/512 1 report_highload > results/report/highload.log 2>&1
cp results/extended/paper_scale_data/manifest.txt results/report/manifest_highload.txt
cp results/extended/paper_scale_data/audit.json results/report/audit_highload.json
for q in 26 27; do
  for rep in 1 2 3; do
    ./cqf/bench_cqf results/extended/paper_scale_data/uniform_positive.bin \
      results/extended/paper_scale_data/uniform_negative.bin "$q" 9 uniform \
      results/report/geometry_control_raw.csv default 63753420 skip-delete >> results/report/geometry_control.log 2>&1
  done
done
python3 scripts/aggregate_results.py results/report/geometry_control_raw.csv results/report/geometry_control.csv
python3 scripts/verify_report_experiments.py
# Preserve a stable completion marker only after every command succeeded.
date -u +%FT%TZ > results/report/COMPLETED.txt
