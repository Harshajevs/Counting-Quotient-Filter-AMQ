# Phase-3: build, reproduce, verify and safely push the expanded AMQ benchmark

This package contains the source and experiment outputs for seven filter
families: CQF, Cuckoo, standard Bloom, Counting Bloom, Blocked Bloom, XOR and a
scalar Binary Fuse-style implementation. It does not contain `.git`; apply it
to an existing clone without touching that clone's `.git` directory.

## 1. Apply the package to your existing repository

1. Unzip the package into a separate directory.
2. Copy the project files into your existing `amq-benchmark` Git clone.
3. Do **not** delete or overwrite `.git`.
4. Do not copy generated binary datasets into Git. The rules in `.gitignore`
   exclude the generated input directories and the compiled benchmark binaries.

Before copying, check that your existing local work is committed or backed up:

```bash
git status --short --branch
git remote -v
```

## 2. Build and run correctness tests

Use Ubuntu 22.04 x86-64 (native Linux or Docker on Apple Silicon with
`--platform linux/amd64`). The CQF reference code uses Linux and x86-specific
instructions. From the project root on an Apple Silicon Mac:

```bash
docker run --platform linux/amd64 --rm -it \
  -v "$(pwd)":/amq-benchmark -w /amq-benchmark ubuntu:22.04 bash
```

Inside the container:

```bash
apt-get update
apt-get install -y build-essential libssl-dev python3 python3-numpy python3-pandas python3-matplotlib
chmod +x scripts/*.sh
./scripts/build_all.sh
./scripts/test_all.sh
python3 -m py_compile scripts/*.py data/generate_data.py
bash -n scripts/*.sh
```

The build produces four executables: CQF, Cuckoo, standard Bloom and the
additional-filter driver. The imported CQF/Cuckoo hash utilities can emit
`-Wimplicit-fallthrough` warnings; the build can still succeed, and those
upstream switch statements should not be changed solely to silence warnings.

## 3. Reproduce the primary seven-filter experiment

The included primary run used one million operations per distribution, three
timing repetitions and a 1/512 target FPR:

```bash
./scripts/run_filter_expansion.sh 1000000 1000000 1/512 3 expanded_1m_1_512
python3 scripts/verify_all_filters.py expanded_1m_1_512 3
```

The command runs CQF, Cuckoo and standard Bloom using the existing common
runner, then Counting Bloom, Blocked Bloom, XOR and Binary Fuse-style using the
same generated 64-bit positive and negative workload files. It writes:

- `additional_filters_<tag>_raw.csv`: repeat-level records for the four added
  families.
- `additional_filters_<tag>.csv`: the four added families aggregated by
  workload.
- `all_filters_<tag>.csv`: unified 14-row comparison (seven filters by two
  distributions).
- `all_filters_<tag>_*.png`: throughput, latency, memory, deletion and FPR
  plots.
- `paper_scale_<tag>*.csv` and configuration: the legacy three-filter rows
  and run metadata used by the merge.

The exact tag of the included primary result is
`expanded_phase3_1m_1_512_v2` (three repetitions). It is retained under
`results/extended/` for reference.

## 4. Reproduce the FPR target checks

The runner supports target FPRs 1/256, 1/512 and 1/1024. Run the complete
three-target sweep at a manageable scale first:

```bash
./scripts/run_filter_expansion_sweep.sh 1000000 1000000 3 expanded
```

For a single target, call `run_filter_expansion.sh` directly and verify its
output tag:

```bash
./scripts/run_filter_expansion.sh 1000000 1000000 1/1024 3 expanded_1_1024
python3 scripts/verify_all_filters.py expanded_1_1024 3
```

## 5. Larger-scale runs

The earlier Phase-2 project includes completed 67M CQF/Cuckoo/Bloom runs at
1/256, 1/512 and 1/1024, plus a near-95%-CQF-load companion point. Those
results are retained. For a new all-seven-filter large-scale run, increase
size gradually, for example:

```bash
./scripts/run_filter_expansion.sh 5000000 1000000 1/512 3 expanded_5m_1_512
python3 scripts/verify_all_filters.py expanded_5m_1_512 3
```

Only after the intermediate run passes should you attempt 67M:

```bash
./scripts/run_filter_expansion.sh 67000000 10000000 1/512 3 expanded_67m_1_512
python3 scripts/verify_all_filters.py expanded_67m_1_512 3
```

This all-seven 67M command is resource-intensive. The generated binary inputs
alone can exceed a gigabyte, and static filter construction uses temporary
arrays that are not included in final filter memory. Allocate ample Docker
memory (preferably 8 GB or more) and disk space. A timeout or allocation
failure is not a result; record partial progress and rerun the affected target
when resources permit. Do not merge partial rows into a complete comparison.

## 6. Regenerate plots from saved CSV outputs

For a unified comparison tag:

```bash
python3 scripts/plot_all_filters.py \
  results/extended/all_filters_expanded_phase3_1m_1_512_v2.csv \
  results/extended/all_filters_expanded_phase3_1m_1_512_v2
```

The original Phase-1/2 plotting scripts and outputs remain available. The
additional scripts include `plot_hash_modes.py`, `plot_hash_scale_comparison.py`,
`plot_extended.py`, `plot_fpr_sweep.py`, `plot_scale_comparison.py`, and
`plot_load_factor_comparison.py`.

## 7. Review and push safely

Exit Docker before using the host Git client:

```bash
exit
```

From the Mac terminal, verify that you are in the existing repository and that
the original remote is still configured:

```bash
git branch --show-current
git remote -v
git status --short --branch
```

The generated dataset directories and compiled executables should be ignored.
Stage only source, tests, scripts, documentation, CSVs and PNGs:

```bash
git add .gitignore README.md PUSH_GUIDE.md FILTER_CATALOG.md THIRD_PARTY_NOTICES.md
git add bloom/ cqf/ cuckoo/ filters/ tests/ data/generate_data.py scripts/
git add results/bench.csv results/bench_raw.csv results/chart_*.png
git add results/extended/*.csv results/extended/*.png results/extended/*.txt results/extended/*.md
```

Audit the exact staging list:

```bash
git diff --cached --check
git diff --cached --stat
git diff --cached --name-only
git diff --cached --name-only | grep -E '(\.bin$|\.o$|\.pyc$|\.npy$|\.npz$|/build/)' || true
```

Do not commit if generated datasets, executables, `.git`, or unrelated local
files appear in the staged list. Once reviewed:

```bash
git commit -m "Expand AMQ benchmark to seven filter families"
git push origin main
git status --short --branch
git log -1 --oneline
```
