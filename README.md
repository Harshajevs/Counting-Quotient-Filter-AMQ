# Seven-filter AMQ research benchmark

This audited package extends the supplied Phase-3 snapshot with a complete
seven-family comparison at **1M and 67M insertion operations**, CQF hash-path
experiments, capacity controls, exact workload auditing, and data-to-LaTeX
figure/table generation. The final 20-page research paper is available as
[a compiled PDF](report/main.pdf), with [editable LaTeX sources](report/main.tex)
and all figures, tables and supporting data under `report/`.

The implementations are CQF, Cuckoo, Bloom, Counting Bloom, Blocked Bloom,
XOR, and a scalar Binary Fuse-style filter. XOR and Fuse-style are immutable
and report preparation/build costs rather than online insertion/deletion.
The four added filters are scalar benchmark variants, not optimized upstream
implementations.

## Evidence included

| Experiment | Operations per distribution | Timing repetitions | Negative queries |
|---|---:|---:|---:|
| Seven filters, target 1/512 | 1,000,000 | 3 | 10,000,000 |
| Seven filters, target 1/512 | 67,000,000 | 3 | 10,000,000 |
| Three CQF hash paths, control | 996,148 | 3 | 10,000,000 |
| Three CQF hash paths, large | 67,000,000 | 3 | 10,000,000 |
| Seven filters, target 1/256 and 1/1024 | 67,000,000 | 1 per target | 10,000,000 |
| CQF compact skewed sensitivity, q=19/r=9 | 67,000,000 | 1 | 10,000,000 |
| CQF matched-N geometry, q=26 vs 27/r=9 | 63,753,420 | 3 per geometry | 10,000,000 |

Both distributions are uniform and finite-universe Zipf (201M, exponent 1.5).
The compact sensitivity is skewed-only; the matched-N geometry control is
uniform-only. The 67M hash study and matched-N control omit deletion by design;
full occurrence deletions remain measured in the main comparison and compact
CQF test. Unsupported and failed-workload operations are unavailable, not zero.

Raw measurements, configuration files and plots are under `results/extended/`.
`results/report/` contains exact dataset audits/hashes, environment, source
hashes, tests, logs and supplementary raw CSVs. The input archive's historical
outputs remain available; they are separate evidence from the new report runs.
The original README is preserved at `docs/README_PHASE3_ORIGINAL.md`.

## Reproduce

The recorded run used Ubuntu 22.04.5 **linux/amd64 via Rosetta on Apple M2**,
GCC/G++ 11.4.0, NumPy 1.21.5, pandas 1.3.5 and Matplotlib 3.5.1. It is not a
native Intel experiment. Source build flags require the corresponding x86
instruction support; no older-CPU portability result is claimed.

From the extracted `amq-benchmark` directory on an Apple Silicon Mac:

```bash
docker run --platform linux/amd64 --rm -it \
  -v "$PWD":/amq-benchmark -w /amq-benchmark ubuntu:22.04
```

Inside the container:

```bash
apt-get update
apt-get install -y build-essential libssl-dev python3 \
  python3-numpy python3-pandas python3-matplotlib time
chmod +x scripts/*.sh
./scripts/test_all.sh
./scripts/run_report_experiments.sh
```

The orchestration script runs every report experiment sequentially and writes
`results/report/COMPLETED.txt` only after supplementary completion checks pass.
It resets previous supplementary CSVs and the old marker at the start. Do not
edit an orchestration script while it is executing. Existing completed CSVs
are included, so regenerating the report assets does not require rerunning the
large benchmarks.

Large generated binary inputs and compiled executables are omitted from this
ZIP. The scripts regenerate them; the recorded seeds, generator versions,
cardinality audits and SHA-256 hashes allow the resulting streams to be
checked. Cuckoo's upstream per-process random hash coefficients are not recorded,
so its exact FPR can vary even for the same workload.

## Regenerate report figures and tables

With the LaTeX project extracted to a separate folder:

```bash
python3 scripts/make_research_assets.py --out /absolute/path/to/latex-project
```

This needs NumPy, pandas and Matplotlib. It creates vector PDF figures, PNG
previews, numeric macros, LaTeX tables and a portable copy of the evidence.
The provided LaTeX ZIP already contains these assets. Open `main.tex` in
Overleaf and compile; the ZIP's README contains compiler instructions.

The revised 20-page edition also includes a detailed target-sweep table and
`data/query_mix_model.csv` in the LaTeX package. The latter combines mean
positive/negative batch costs under explicitly stated query fractions. It is
an analytical model from the existing measurements, not a mixed-query timing.

## Interpretation

- Primary CQF and Cuckoo tables are sized from requested operations; the other
  five use exact distinct cardinality as offline sizing knowledge. The compact
  CQF run is a separately labelled sensitivity point.
- CQF power-of-two capacity jumps matter: 996,148 operations fit near 95% in
  2^20 slots, exactly 1M uses 2^21, and 67M uses 2^27 at about 50% load.
- The default CQF uses MurmurHash64A and runtime range reduction. Invertible
  mode is limited to the configured key width. The external SplitMix64-style
  path is recomputed inside each timed operation and uses QF_HASH_NONE afterward.
  The study measures the complete hash-and-CQF path, not isolated mixer latency.
- Repeated timing queries do not multiply the independent FPR sample size.
  The report uses first-run Wilson intervals with 10M negatives and preserves
  the Cuckoo repeat range.
- Memory is final filter storage, with estimated Counting Bloom map overhead.
  It excludes input arrays, graph workspaces and whole-process peak RSS.
- Fuse-style uses a guard fingerprint bit; achieved FPR is not identical to XOR.
  Batch time per operation is an average, not a percentile-latency measurement.

See `docs/REPORT_AUDIT.md` for changes and limitations, `FILTER_CATALOG.md`
for algorithm scope, and the paper for the comparisons with the earlier report
and published reference values. This extends project head `fe184baa6933`
with the supplied Phase-3 implementation and the audited final-report work.
Upstream CQF and Cuckoo licenses are retained in their directories. Historical
provenance notes describe the report-generation snapshot before publication.
