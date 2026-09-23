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

`run_all.sh` takes optional arguments if you want a different scale:

```bash
./scripts/run_all.sh <N> <UNIVERSE> <SKEW> <NEG>
# e.g. a smaller/faster run:
./scripts/run_all.sh 300000 60000 1.5 30000
```

This will:
1. Generate `results/data/{uniform,zipf}_{positive,negative}.txt` — the exact same
   key files all three filters are benchmarked on.
2. Build `cqf/bench_cqf`, `cuckoo/bench_cuckoo`, `bloom/bench_bloom`.
3. Run each filter on both the uniform and Zipfian datasets, appending one row
   per run to `results/bench.csv`.
4. `plot_results.py` reads that CSV and writes four PNG charts into `results/`:
   `chart_insert_throughput.png`, `chart_query_throughput.png`,
   `chart_memory.png`, `chart_false_positive_rate.png`.

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
