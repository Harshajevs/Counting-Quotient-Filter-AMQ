# AMQ Benchmark Suite — Bloom vs. Cuckoo vs. Counting Quotient Filter

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
apt-get install -y build-essential libssl-dev python3 python3-numpy python3-matplotlib
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
