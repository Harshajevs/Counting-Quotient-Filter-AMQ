# AMQ Benchmark Suite — Comparative Evaluation of Seven Approximate Membership Filters

A reproducible benchmark suite for comparing a Bloom filter, a Cuckoo filter,
and the Counting Quotient Filter (CQF) under the uniform-random and Zipfian
workloads used in the Counting Quotient Filter research paper.

The benchmark measures insertion, successful lookup, negative lookup,
deletion, memory usage, and measured false-positive rate. The three filters
consume the same generated uint64 input files so that the workload itself is
controlled across implementations.

## What was fixed

This version contains the corrections made after auditing the original code
against the paper's benchmark methodology and the observed CSV/plots.

### 1. CQF sizing was causing the biggest discrepancy

The old `run_all.sh` used:

```text
ceil(log2(N / 0.9))
```

For `N = 1,000,000`, this selected `2^21 = 2,097,152` CQF slots, so the
filter was only about 47.7% occupied. That doubled the CQF memory footprint
and substantially changed the CQF insert/lookup behavior.

The benchmark now selects the smallest power-of-two CQF table capable of the
requested workload and limits the common benchmark size to the reference
CQF's ~95% usable point. For the default 1M target this gives:

```text
CQF slots        = 2^20 = 1,048,576
benchmark ops    = 996,148
occupancy        ~= 95%
CQF qbits/rbits  = 20 / 9
```

All three filters start from the same 996,148-operation input stream.
The Cuckoo/Zipfian case is intentionally allowed to stop early when its
duplicate-handling limit is reached, matching the paper's reported failure mode.

### 2. Bloom was not configured like the paper

The old benchmark hard-coded `k=4` and used about 16.95 bits/item. The paper's
space comparison uses the Bloom filter configured as small as possible for the
target FPR with the optimal integer number of hash functions.

The benchmark now uses the optimal configuration for `1/512`:

```text
bits/item ~= 12.984
hash functions = 9
```

For the default run this is about 1.62 MB, matching the paper's theoretical
space scale much more closely.

### 3. Bloom timing included string conversion

The old Bloom benchmark called `std::to_string()` inside every timed insert and
lookup. That measured key conversion/allocation as well as Bloom operations,
while CQF and Cuckoo received raw integers.

Bloom now accepts `uint64_t` directly. Its bit array is stored in `uint64_t`
words rather than `std::vector<bool>`, and the filter uses two fast 64-bit base
hashes with Kirsch-Mitzenmacher double hashing.

### 4. CQF Zipfian deletion was being benchmarked incorrectly

`qf_delete_key_value()` removes the entire counter for a key in a single call.
Calling that once for every repeated Zipfian input operation makes the first
occurrence delete the count and most later calls become no-ops. The resulting
throughput is not a per-delete measurement.

The benchmark now uses `qf_remove(..., 1, ...)` once per inserted occurrence.
Thus a key occurring 100 times is decremented 100 times. A post-delete check
also verifies that all inserted occurrences have been removed.

### 5. Zipf generation now matches the paper's scale without an enormous CDF

The paper describes a Zipf coefficient of 1.5 and uses a universe of about
201 million items in the skewed-data experiment. The old Python generator
constructed a complete floating-point CDF, which is impractical at that
universe size.

The generator now uses NumPy's discrete Zipf sampler with rejection of the
rare tail above the finite universe bound. Repeated ranks are mapped to stable,
well-mixed uint64 keys. The generated manifest records the distinct-key count
and maximum frequency so the skewed workload can be audited directly.

### 6. CQF rank/select CPU detection was corrected

The original CQF source enabled PDEP/TZCNT using the `__SSE4_2__` preprocessor
symbol even though these are BMI instructions. The revised code uses runtime
CPU detection for BMI/BMI2 and retains the original broadword select
implementation as a fallback. POPCNT uses the compiler intrinsic.

This keeps the benchmark compatible with x86-64 Linux while still using the
paper's intended fast rank/select path on supported processors.

## Paper-aligned configuration

The paper configures its structures for a false-positive target of `1/512`.
Its Table 1 reports approximately:

```text
                 CQF       Cuckoo       Bloom
uniform insert   11.19M    14.25M       2.84M ops/s
success lookup   11.16M    18.87M       2.55M ops/s
random lookup    25.93M    18.84M      11.56M ops/s
bits/item        11.71     12.631       12.984
```

Those are hardware- and implementation-specific reference numbers, not
universal speed limits. The paper's experiments were performed on Intel
Skylake hardware with a much larger in-memory workload. A 1M-key run on a
modern machine can therefore have substantially different absolute throughput
while still reproducing the important qualitative behavior.

## Layout

```text
cqf/                 CQF reference implementation + benchmark driver
cuckoo/              Cuckoo filter reference implementation + driver
bloom/                corrected compact Bloom filter + driver
data/                 shared workload generator
scripts/              build, run, aggregate, plot, and regression-test scripts
tests/                lightweight CQF counting/deletion regression test
results/              validated CSVs and generated charts
```

## Build and run on Apple Silicon Macs

The CQF implementation is Linux/x86-64 oriented. On an Apple Silicon Mac,
run the benchmark inside an x86-64 Ubuntu container:

```bash
docker run --platform linux/amd64 --rm -it \\
  -v "$(pwd)":/amq-benchmark ubuntu:22.04
```

Inside the container:

```bash
cd /amq-benchmark
apt-get update
apt-get install -y build-essential libssl-dev python3 python3-numpy python3-pandas python3-matplotlib
chmod +x scripts/*.sh
./scripts/test_all.sh
./scripts/run_all.sh
python3 scripts/plot_results.py
```

The generated binaries and datasets are intentionally not part of the Git
history. `results/bench.csv`, `results/bench_raw.csv`, and the PNG charts are
kept so that the evaluated result set can be inspected and reproduced.

Optional arguments:

```bash
./scripts/run_all.sh <TARGET_N> <ZIPF_UNIVERSE> <SKEW> <NEGATIVE_QUERIES> <REPEATS>
```

The defaults are:

```text
TARGET_N          1,000,000
ZIPF_UNIVERSE     201,000,000
SKEW              1.5
NEGATIVE_QUERIES  100,000
REPEATS           3
```

## What the benchmark is intended to demonstrate

The comparison should be interpreted feature-by-feature, not as a claim that
CQF is always the fastest possible RAM data structure for every operation.
The paper itself reports that Cuckoo has comparable RAM performance and that
CQF is designed to combine speed with counting, deletion, compact space,
resizing, merging, and good behavior on skewed data.

The particularly important qualitative checks are:

- CQF remains usable on duplicate-heavy Zipfian input.
- Cuckoo can fail early on the same duplicate-heavy workload.
- CQF supports deletion/counting while a plain Bloom filter does not.
- CQF remains close to the requested high-load operating point.
- measured false-positive rates stay at or below the theoretical bound.
- CQF space is below the Cuckoo space at the paper's target error rate.

The Bloom and Cuckoo negative-query rates on the Zipfian workload can be much
lower than `1/512`. That is not a contradiction: `1/512` is an upper/configured
false-positive target, while a heavily duplicated workload contains far fewer
distinct stored keys, so the realized occupancy and collision probability can
be substantially lower.

## Validated result from this corrected version

The corrected code was rebuilt and run for 3 repetitions on x86-64 Linux with:

```text
benchmark operations = 996,148
CQF                   = 2^20 slots, rbits=9
Cuckoo                = 12-bit fingerprints, 4-way buckets
Bloom                 = 12.984 bits/item, k=9
Zipf universe         = 201M
Zipf skew             = 1.5
negative queries      = 100,000
```

The resulting aggregate measurements in `results/bench.csv` show:

```text
Metric                    Uniform                         Zipfian
CQF memory                1,472,416 B                    1,472,416 B
Cuckoo memory             1,572,864 B                    1,572,864 B
Bloom memory              1,616,784 B                    1,616,784 B
CQF insert                10.53M ops/s                   19.26M ops/s
CQF positive lookup       21.88M ops/s                   27.74M ops/s
CQF negative lookup       28.74M ops/s                   57.33M ops/s
CQF delete                4.94M ops/s                    15.27M ops/s
Cuckoo inserts accepted   996,148                        24
Bloom inserts accepted    996,148                        996,148
```

These numbers should be treated as a validation run on the development x86-64
machine rather than as a promise of identical throughput on another CPU or
virtualization layer.

## Regression testing

Run:

```bash
./scripts/test_all.sh
```

The regression suite currently checks:

1. CQF counting for repeated keys and exact one-at-a-time decrement/delete
   behavior.
2. Zipf workload generation at a 201M universe without building a 201M-entry
   CDF.
3. Negative queries are disjoint from the corresponding positive key set.

`run_all.sh` also checks the output shape, positive lookup correctness, and
successful deletion count for every raw benchmark row.

## Output files

`results/bench_raw.csv` contains every individual timed repetition. With the
default 3 repetitions it contains 18 data rows (3 repeats × 6
filter/distribution configurations).

`results/bench.csv` contains the arithmetic mean of each timed quantity across
repetitions and one row for each of the six configurations.

The plotting script generates:

```text
chart_insert_throughput.png
chart_query_throughput.png
chart_query_neg_throughput.png
chart_delete_throughput.png
chart_memory.png
chart_false_positive_rate.png
chart_fp_ratio.png
chart_capacity.png
chart_dashboard.png
```

## Honest limitations

This benchmark is a one-point high-load comparison rather than the complete
5%-to-95% load-factor sweep in Figures 6–9 of the paper. It also does not yet
reproduce the paper's SSD, multi-threaded, merge, or application benchmarks.
Absolute throughput therefore should not be treated as a byte-for-byte
reproduction of the paper. The purpose of this phase is to establish a sound,
shared benchmark harness and reproduce the major in-memory qualitative trends
without hiding cases where the implementations differ.

## Phase 2: paper-scale and CQF hash-mode experiments

The Phase-1 files in `results/bench.csv` and `results/chart_*.png` are retained.
The new experiments write to `results/extended/` so that the original baseline
is not overwritten.

### 1. CQF hash-mode study

The CQF reference implementation exposes `QF_HASH_DEFAULT`,
`QF_HASH_INVERTIBLE`, and `QF_HASH_NONE`. The benchmark driver now accepts an
optional final argument (`default`, `invertible`, or `none`) and records the
mode in `config_param`.

```bash
./scripts/run_hash_study.sh 996148 10000000 201000000 1.5 3
```

This runs all three modes on uniform and Zipfian data and writes:

- `results/extended/hash_modes_raw.csv`
- `results/extended/hash_modes.csv`
- `results/extended/hash_modes_configuration.txt`
- `results/extended/hash_throughput_uniform.png`
- `results/extended/hash_throughput_zipfian.png`
- `results/extended/hash_false_positive_rate.png`

**Hash-mode interpretation and limitations.** The workload generator creates
64-bit keys, while the CQF is configured with `key_bits = qbits + rbits`.
`INVERTIBLE` is truly collision-free only when the input key domain fits that
configured width. In this experiment, wide 64-bit inputs are mapped to the
CQF's smaller key domain, so the expected collision probability is
approximately `distinct_keys / 2^(qbits+rbits)`; it must not be described as
zero. `NONE` uses a deterministic SplitMix64 pre-hash to the same key width.
The external SplitMix64 transformation is performed inside the timed insert,
lookup, and delete loops, so `NONE` throughput includes its hashing cost just
as the other modes include internal hashing. The measured comparison is
therefore end-to-end for the key mapping plus CQF operation. The script also
accepts an optional sixth output tag so a different scale can be run without
overwriting the control results. For example:

```bash
./scripts/run_hash_study.sh 67000000 10000000 201000000 1.5 3 67m skip-delete
python3 scripts/plot_hash_modes.py 67m
```

The package contains both the 996,148-operation control and a completed
67M-operation hash-mode study. The 67M run uses three timing repetitions for
all six mode/workload combinations and 10M negative queries. Its outputs are:

- `results/extended/hash_modes_67m_raw.csv` and `hash_modes_67m.csv`
- `results/extended/hash_modes_67m_configuration.txt`
- `results/extended/hash_throughput_uniform_67m.png`
- `results/extended/hash_throughput_zipfian_67m.png`
- `results/extended/hash_false_positive_rate_67m.png`

At 67M, the experiment focuses on insert, positive lookup, negative lookup
and FPR. One-at-a-time CQF deletion is omitted for this large-scale hash-mode
study (`NA` in its CSV); deletion remains measured in the 996k hash-mode
control and in the cross-filter 67M comparisons. This keeps the hash-mode
comparison focused on hash cost and accuracy while avoiding the very long
high-scale delete path. The 67M hash-mode runner accepts `skip-delete` as its
seventh argument and reuses a matching generated workload instead of
regenerating multi-gigabyte input files for every retry:

```bash
./scripts/run_hash_study.sh 67000000 10000000 201000000 1.5 3 67m skip-delete
python3 scripts/plot_hash_modes.py 67m
python3 scripts/plot_hash_scale_comparison.py
```

`hash_scale_comparison.csv` and `hash_scale_comparison_throughput.png`
compare the 996k control against 67M. This is a scale/configuration comparison,
not a pure cache-only comparison: the CQF geometry changes from `qbits=20`
to `qbits=27`, and uniform load changes from about 95% to about 49.9%.

The theoretical column uses the workload-specific random-collision estimate
`distinct_keys / 2^(qbits+rbits)`. At a near-95% CQF load this is close to
`0.95 * 2^-rbits`; on Zipfian input it falls with the distinct-key count.
This is more informative than plotting the configured target as though it
were the exact expected rate for every workload.

The theoretical values for `INVERTIBLE`/`NONE` use the CQF's actual number of
distinct stored keys divided by the configured hash domain. Measured FPR is
based on the independently generated negative query sample; at low FPRs,
finite-sample uncertainty is substantial. Increase the negative query count
for more precise accuracy comparisons.

### 2. Paper-scale comparison (67 million insert operations)

```bash
./scripts/run_fpr_sweep.sh 67000000 10000000 1 3
```

This sweep uses the paper's 67M-scale workload, Zipf universe of 201M and
skew 1.5 at targets 1/256, 1/512 and 1/1024. It uses one timing pass at
1/256 and 1/1024 and three at 1/512, with 10M negative queries at every
target. It selects the next power-of-two
CQF table that can hold the complete workload below the 95% fullness guard.
For 67M unique uniform keys this is 2^27 slots, so actual occupancy is about
49.9%, not 95%; this is recorded in each `paper_scale_*_configuration.txt`.
The runner benchmarks CQF, Cuckoo and Bloom on the same generated input and
writes only under `results/extended/`:

- per-target raw and aggregated CSVs (`paper_scale_1_256.csv`, etc.)
- throughput plots for insert, positive lookup, negative lookup and delete
- per-target measured-vs-theoretical FPR charts
- FPR-sweep charts comparing all three target settings
- per-target configuration files documenting slots, load factor and filter sizing

The data generator writes binary uint64 datasets in chunks and keeps only a
compact Zipf-rank frequency map, avoiding a giant Python set and multi-gigabyte
text conversion. The benchmark drivers load binary datasets into memory, so the
67M run still needs substantial RAM and roughly 1.1 GB for the four binary input
files plus result/working space. After the 1/512 result is present, run `python3 scripts/plot_scale_comparison.py`
to compare the 996k Phase-1 baseline with the 67M run. This creates
`scale_comparison.csv` plus throughput, memory and FPR comparison charts.
Do not commit generated `paper_scale_data/`, `hash_data/`, or tagged `hash_data_*/` directories.

A second run isolates the CQF power-of-two capacity jump by putting a 2^26-slot
CQF close to its 95% fullness limit. It is just under 67M operations and is
written to a separate tag so it cannot overwrite the exact 67M results:

```bash
./scripts/run_paper_scale.sh 63753420 10000000 1/512 1 highload_1_512
python3 scripts/plot_load_factor_comparison.py
```

The additional outputs are `paper_scale_highload_1_512.*` and
`cqf_load_factor_comparison.csv` / `cqf_load_factor_*.png`.

Bloom's theoretical FPR now uses the exact distinct inserted-key count from the
generator manifest, not the number of insertion operations. This is essential
for duplicate-heavy Zipf input: repeated insertions do not set new Bloom bits.

### 3. Regression tests and environment

```bash
./scripts/test_all.sh
./scripts/build_all.sh
```

Run inside Ubuntu 22.04 x86-64 (the CQF implementation uses x86-specific
instructions and Linux headers). On Apple Silicon, use the existing Docker
workflow with `--platform linux/amd64`.

The imported Cuckoo and CQF hash utility sources may emit intentional
`-Wimplicit-fallthrough` warnings. The benchmark build succeeds; do not alter
the imported hash switch statements merely to silence these warnings.

## Expanded seven-filter comparison

The benchmark now includes four additional AMQ families alongside CQF,
Cuckoo and standard Bloom: Counting Bloom, Blocked Bloom, XOR and a scalar
Binary Fuse-style filter. The dynamic/static distinction is explicit: XOR and
Binary Fuse are immutable and are measured by preprocessing, build and query
time, not by invented online insert/delete rates. The unified comparison
also includes average latency derived from each timed batch. The new filters
are scalar reference implementations for a reproducible common benchmark;
the Binary Fuse-style implementation is not the optimized authors' reference
implementation, so published absolute throughput figures are not directly
comparable.

See [`FILTER_CATALOG.md`](FILTER_CATALOG.md) for the filter capability matrix,
capacity/FPR methodology, limitations, references and reproducible commands.
Run a single unified comparison with:

```bash
./scripts/run_filter_expansion.sh 1000000 1000000 1/512 3 expanded_1_512
```

Run all three target FPRs with:

```bash
./scripts/run_filter_expansion_sweep.sh 1000000 1000000 3 expanded
```


## Phase 3: expanded seven-filter comparison

The benchmark now compares seven filter families under a common uniform and
Zipfian workload:

1. Counting Quotient Filter (CQF)
2. Cuckoo filter
3. Standard Bloom filter
4. Counting Bloom filter
5. Blocked Bloom filter
6. XOR filter
7. Binary Fuse-style scalar filter

The four new filters are self-contained C++17 scalar reference
implementations in `filters/amq_extra.hpp`. Counting Bloom supports
one-occurrence-at-a-time deletion with packed four-bit counters and an exact
overflow side table. Blocked Bloom groups bits into 512-bit blocks to improve
cache locality. XOR and Binary Fuse-style are immutable filters built from a
batch of distinct keys; their construction time and positive/negative query
latency are measured, while incremental insert/delete are explicitly `NA`.
The Binary Fuse-style implementation is not the authors' optimized reference
implementation or a bit-for-bit reproduction. Do not compare its absolute
throughput directly with optimized published implementations.

### Common benchmark and outputs

The runner feeds all seven families the same positive uniform/Zipfian streams
and negative query streams, records repeat-level raw data, aggregates means,
and produces a 14-row combined table (seven filters by two distributions).
The comparison reports operation support, insertion or construction time,
positive and negative lookup throughput and mean latency, deletion where
supported, memory, measured FPR and an implementation-specific theoretical
estimate. Static filters report preprocessing and build-only timing as well
as end-to-end construction latency so deduplication is not hidden.

Run the primary seven-filter comparison (1M operations, three timing repeats,
1/512 target):

```bash
./scripts/run_filter_expansion.sh 1000000 1000000 1/512 3 expanded_1m_1_512
python3 scripts/verify_all_filters.py expanded_1m_1_512 3
```

Run all three FPR targets:

```bash
./scripts/run_filter_expansion_sweep.sh 1000000 1000000 3 expanded
```

The 67M legacy-filter Phase-2 experiments are retained. The new seven-filter
runner can also be invoked at larger sizes, but the all-seven 67M workload
should be treated as a separate resource-intensive experiment: test an
intermediate size first, provision ample Docker memory and disk, and do not
assume static construction peak memory is represented by the final filter
footprint.

See [`FILTER_CATALOG.md`](FILTER_CATALOG.md) for algorithms, operation
semantics, capacity/FPR rules, research references and limitations. See
[`results/extended/PHASE3_STATUS.md`](results/extended/PHASE3_STATUS.md) for
the included completed run, machine context, results summary and validation
record.
