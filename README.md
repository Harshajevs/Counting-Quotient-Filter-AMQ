# AMQ Benchmark Suite — Bloom vs. Cuckoo vs. Counting Quotient Filter

A common benchmarking setup that runs the Bloom filter, cuckoo filter, and counting
quotient filter (CQF) through the exact same input data, timing insertion, lookup,
and deletion separately, tracking memory usage, and checking the measured
false-positive rate against each filter's own theoretical rate.

This is the code behind the **Reproduction / Benchmarking extension** track of the
project. All three filters read from the *same* generated key files, so the
comparison is apples-to-apples rather than each filter being benchmarked on its
own separately-generated data.

## Layout

```
cqf/                CQF library (from the paper's own reference implementation)
  ├── include/       public headers (gqf.h, gqf_int.h, ...)
  ├── src/           gqf.c, hashutil.c, partitioned_counter.c, zipf.c
  └── bench_cqf.c    our unified benchmark driver

cuckoo/              cuckoo filter library (Fan et al.'s reference implementation)
  ├── src/           cuckoofilter.h and supporting headers (header-only library)
  └── bench_cuckoo.cc  our unified benchmark driver

bloom/
  ├── bloom_filter.hpp   minimal reference Bloom filter (4 hash functions, bit array)
  └── bench_bloom.cc     our unified benchmark driver

data/
  └── generate_data.py   generates the shared uniform + Zipfian key files

scripts/
  ├── build_all.sh       compiles all three benchmark binaries
  ├── run_all.sh         generates data, builds, and runs the full experiment
  └── plot_results.py    turns results/bench.csv into comparison charts

results/               output lands here: bench.csv + PNG charts (gitignored except .gitkeep)
```

## What each filter is missing (so the CSV schema makes sense)

- **Bloom filter**: no delete support at all — this is one of the exact gaps the
  CQF paper points out. Its CSV rows have `deleted_ok = 0` and delete-time columns
  set to 0 rather than silently dropping the columns, so the limitation is visible
  in the data itself, not just in prose.
- **Cuckoo filter**: supports delete, but each bucket can only hold a small, fixed
  number of duplicate entries (4 slots × 2 candidate buckets). On the Zipfian
  workload, where one key can appear tens of thousands of times, the filter fills
  up and starts rejecting inserts almost immediately — this is a real, measured
  result in our run (29 successful inserts before failure), not a bug, and it
  matches the paper's own finding that the cuckoo filter cannot handle
  heavily-skewed data.
- **CQF**: supports all three operations at full scale, including on the Zipfian
  workload, because repeated items are encoded as a compact counter instead of
  being stored as separate duplicate entries.

## How to reproduce

Requirements: `gcc`/`g++` (C11/C++11), `python3` with `numpy` and `matplotlib`,
and `libssl-dev` (the CQF library links against OpenSSL).

```bash
# from the repo root
pip install numpy matplotlib          # if not already installed

./scripts/run_all.sh                  # default: 1,000,000 keys, Zipfian skew=1.5
python3 scripts/plot_results.py       # writes charts into results/
```

`run_all.sh` takes optional arguments if you want a different scale or more/fewer repeats:

```bash
./scripts/run_all.sh <N> <UNIVERSE> <SKEW> <NEG> <REPEATS>
# e.g. a smaller/faster run with 5 repeats instead of the default 3:
./scripts/run_all.sh 300000 60000 1.5 30000 5
```

This will:
1. Generate `results/data/{uniform,zipf}_{positive,negative}.txt` — the exact same
   key files all three filters are benchmarked on.
2. Build `cqf/bench_cqf`, `cuckoo/bench_cuckoo`, `bloom/bench_bloom`.
3. Run each filter on both the uniform and Zipfian datasets, **REPEATS times each**
   (default 3), appending every run to `results/bench_raw.csv`.
4. Average the repeats into one stable `results/bench.csv` via
   `scripts/aggregate_results.py` (see "Diagnosis" section below for why this
   matters — single-run timing numbers can be noisy).
5. `plot_results.py` reads `bench.csv` and writes eight PNG charts into `results/`:
   - `chart_insert_throughput.png`, `chart_query_throughput.png`,
     `chart_query_neg_throughput.png`, `chart_delete_throughput.png` — timing
   - `chart_memory.png` — space usage
   - `chart_false_positive_rate.png`, `chart_fp_ratio.png` — accuracy
   - `chart_capacity.png` — requested vs. actually-inserted keys (makes the
     cuckoo-filter-on-Zipfian failure visible at a glance)
   - `chart_dashboard.png` — all of the above combined into one slide-ready figure

## Running a single filter by hand

Each binary can also be run directly, which is useful for testing one
configuration at a time:

```bash
# CQF:     <pos_file> <neg_file> <qbits> <rbits> <distribution_label> <out_csv>
./cqf/bench_cqf results/data/uniform_positive.txt results/data/uniform_negative.txt 20 9 uniform results/bench.csv

# Cuckoo:  <pos_file> <neg_file> <capacity> <bits_per_item[8|12|16]> <distribution_label> <out_csv>
./cuckoo/bench_cuckoo results/data/uniform_positive.txt results/data/uniform_negative.txt 200000 12 uniform results/bench.csv

# Bloom:   <pos_file> <neg_file> <size_bits> <num_hashes> <distribution_label> <out_csv>
./bloom/bench_bloom results/data/uniform_positive.txt results/data/uniform_negative.txt 2000000 4 uniform results/bench.csv
```

## CSV schema (identical across all three filters)

```
filter, distribution, n_requested, n_inserted, config_param, memory_bytes,
insert_time_s, insert_ops_sec,
query_pos_time_s, query_pos_ops_sec, found_positive,
query_neg_time_s, query_neg_ops_sec,
measured_fp_rate, theoretical_fp_rate, fp_ratio,
delete_time_s, delete_ops_sec, deleted_ok
```

`n_inserted` can be less than `n_requested` if a filter fills up before all keys
are inserted (this is expected and, on the Zipfian workload, is itself one of
the headline results — see above).

## Diagnosis: were the first results correct?

A first run of this suite (before the fixes below) produced three things that
looked like they might be bugs. Here's what each one actually was, checked
against the code rather than assumed:

**1. CQF's insert throughput looked suspiciously slow next to cuckoo's (a
~17x gap, vs. the paper's own ~1.27x gap).** This was **not a bug in the
benchmark code**. Re-running the exact same binaries on a different machine
produced only a ~2x gap — much closer to the paper. Absolute ops/sec numbers
are sensitive to the specific CPU, background load, and virtualization layer
you're running on, so a single run on a shared/throttled container can look
far slower than expected without anything being wrong. `run_all.sh` now
**runs every filter/config 3 times by default and averages the results**
(`scripts/aggregate_results.py`) specifically to smooth out this kind of
run-to-run noise. If you still see a large gap after averaging, re-run with
`REPEATS=5` or more and check nothing else heavy is running on the machine
at the same time.

**2. The Zipfian false-positive chart showed ~0 measured FP for Bloom and
cuckoo, but a small non-zero value for CQF, while all three "theoretical"
bars looked identical.** This is **correct, expected behavior, not an
inconsistency**. The theoretical bars are identical because all three
filters were deliberately configured to target the same ~1/512 rate. The
measured bars are near-zero because the Zipfian dataset is extremely skewed:
out of 1,000,000 insert *operations*, only about **12,500 are actually
distinct keys** (the rest are repeats of those same ~12,500 items — see
`results/data/manifest.txt` after a run). With that few distinct fingerprints
occupying the filter, the real chance of a random collision is far below the
theoretical worst-case rate, which assumes the filter is holding as many
distinct items as its target capacity. CQF shows a (still tiny) non-zero
value because it's the only one of the three that successfully retains
representations of all ~12,500 distinct items — cuckoo only got 29 of them
in (see point 3), so it has even less chance of a collision.

**3. The cuckoo filter inserted only 29 keys out of 1,000,000 on the Zipfian
dataset.** This is also **correct, expected, and in fact the headline
result of this whole comparison**: cuckoo filters can only store a small,
fixed number of duplicates of any one key (bucket size x number of candidate
buckets). Zipfian data concentrates massively on a few keys, so the filter
fills up and starts rejecting inserts almost immediately. The paper reports
the same failure mode (~200 inserts before failure in their setup). See
`chart_capacity.png` for a chart built specifically to make this visible.

**4. The Bloom filter's measured false-positive rate was consistently ~1.44x
its theoretical rate on uniform data — this one *was* a real bug, now
fixed.** `bloom_filter.hpp`'s third and fourth hash functions used the exact
same recurrence (`hash = hash*31 + c`), differing only in their starting
seed, which made them far more correlated than genuinely independent hash
functions should be — inflating the real false-positive rate above what the
textbook k-hash formula predicts. This has been replaced with the standard
**Kirsch-Mitzenmacher double-hashing** technique (`g_i(x) = h1(x) + i*h2(x)
mod m`), which only needs two genuinely different base hashes to simulate k
independent ones. After the fix, measured FP rate on uniform data is 0.988x
theoretical (previously 1.44x) — confirmed by rebuilding and re-running.

## Known simplifications / honest caveats

- The Zipfian generator (`data/generate_data.py`) implements the standard
  rank-based discrete Zipfian distribution and maps ranks to well-spread 64-bit
  keys via a splitmix64 mixer, rather than reusing the CQF repo's own
  `zipf.c`/`zipf.h` generator (present in `cqf/src/` but not currently wired into
  `bench_cqf.c`). Using one shared Python generator for all three filters was
  simpler and guarantees byte-identical input across filters; switching to the
  repo's C generator is a possible follow-up if closer fidelity to the paper's
  own data-generation code is wanted.
- Cuckoo filter fingerprint size (`bits_per_item`) and CQF's remainder size
  (`rbits`) are configured to similar theoretical false-positive rates, but the
  two filters compute that rate differently (cuckoo: `2*assoc/2^bits`, CQF:
  `2^-rbits`), so treat the false-positive comparison as "both filters roughly
  targeting a similar rate," not as identical configurations.
- This suite reports a single configuration's aggregate throughput per run,
  not a full load-factor sweep (the paper's own Figures 6–8 show throughput
  *as the filter fills up*, from 5% to 95% load in 5% steps). Reproducing that
  specific sweep would mean re-running each filter at many intermediate stopping
  points and is a natural next step, not something this version does.
