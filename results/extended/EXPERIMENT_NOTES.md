# Phase-2 experimental results and interpretation

## Scope

This phase implements the two algorithmic/reproduction directions selected in
Section 6 of the project report: (1) test the filters at approximately 67M
insertion operations and at multiple false-positive targets, and (2) compare
CQF's three reference hash modes on the same uniform and duplicate-heavy
workloads. The application interface, locking-granularity and merge-heap
tracks remain out of scope for this phase.

The Phase-1 files (`results/bench.csv` and `results/chart_*.png`) are retained
unchanged. All new outputs live in `results/extended/`.

## Environment and workload

- Execution host reported by the Linux benchmark container: AMD EPYC 9V74,
  5 available CPU cores, 32 MiB L3 cache, x86-64 Linux. This is not the
  SIGMOD paper's Intel Skylake test machine, so absolute Mops/s should not be
  equated with the paper's numbers.
- Paper-scale workload: 67,000,000 insertion operations per distribution.
- Zipf generator: finite universe 201,000,000, exponent 1.5, seed 42.
- Distinct keys: 67,000,000 uniform and 229,118 Zipfian in the 67M run.
- Negative queries: 10,000,000 independently generated non-member keys per
  distribution. The same fixed input sample is reused across timing repeats.
- FPR targets: 1/256, 1/512 and 1/1024. The 1/256 and 1/1024 runs are one
  timing pass each; the central 1/512 result is averaged over three timing
  passes. Hash modes are also averaged over three timing passes.
- All filter drivers consume the same binary uint64 input sets. Input
  generation is excluded from operation timings. Drivers validate positive
  lookup counts and deletions after timing.

## Capacity rounding is part of the result

The CQF uses a power-of-two number of slots and enforces a 95% fullness
threshold. For 67M distinct uniform keys, a 2^26 table would exceed that
threshold, so the runner must choose 2^27 = 134,217,728 slots. That makes the
actual uniform distinct-key load 49.9189%, not 95%. The 67M experiment is
therefore a valid beyond-cache workload, but it is not a 95%-occupied CQF
experiment.

To isolate this table-size discontinuity, a supplementary high-load point
uses 63,753,420 operations, the largest integer below 95% of 2^26 slots. Its
CQF uses 67,108,864 slots and reaches approximately 95% distinct-key load.
It is separately labelled `paper_scale_highload_1_512` and does not replace
any 67M result.

## CQF hash-mode study (996,148 operations, 10M negative queries)

The exact Phase-1 CQF geometry is retained (`qbits=20`, `rbits=9`). Results
below are means of three timing repetitions; FPRs use one deterministic
10M-query negative sample and therefore do not gain independent-sample power
from timing repetition.

| Workload | Hash mode | Insert (M/s) | Positive lookup (M/s) | Negative lookup (M/s) | Delete (M/s) | Measured FPR | Expected FPR |
|---|---|---:|---:|---:|---:|---:|---:|
| Uniform | DEFAULT (Murmur64A) | 9.96 | 19.82 | 26.82 | 4.81 | 0.0018458 | 0.0018555 |
| Uniform | INVERTIBLE (`hash_64`) | 10.42 | 19.83 | 30.75 | 5.05 | 0.0018633 | 0.0018555 |
| Uniform | NONE + SplitMix64 | 11.14 | 26.04 | 34.28 | 4.87 | 0.0018648 | 0.0018555 |
| Zipfian | DEFAULT (Murmur64A) | 19.72 | 25.96 | 90.73 | 15.27 | 2.63e-5 | 2.62e-5 |
| Zipfian | INVERTIBLE (`hash_64`) | 19.92 | 33.38 | 111.99 | 15.06 | 3.09e-5 | 2.62e-5 |
| Zipfian | NONE + SplitMix64 | 19.40 | 32.91 | 134.30 | 13.87 | 2.60e-5 | 2.62e-5 |

`NONE` applies a deterministic SplitMix64 pre-hash inside the timed
insert/lookup/delete loops, so its end-to-end timings include the external
hashing work. `INVERTIBLE` is only collision-free when the input domain fits
the configured hash width; these 64-bit keys are reduced to a 29-bit CQF
hash domain. The expected random-collision estimate is
`distinct_keys / 2^(qbits+rbits)` for all three modes, not zero.

On this host, `NONE` gave the best uniform lookup throughput; `INVERTIBLE`
was strongest for Zipf positive lookups; and no mode wins every operation.
Zipf `INVERTIBLE` measured FPR is about 18% above the estimate on this one
negative-query sample. That warrants additional independent seeds before
claiming a systematic bias; it is not enough evidence on its own to reject
that mode. The 996k hash-mode table is the cache-sized control study directly comparable
to Phase 1. A second tagged 67M study was completed with three timing
repetitions for each mode/workload. At this scale, deletion is deliberately
omitted (`NA` in the CSV) so the study isolates hashing in insert, positive
lookup, negative lookup and FPR. The 996k hash-mode control continues to
measure deletion, and deletion is also retained in the separate cross-filter
67M comparison.

## CQF hash-mode study at 67M operations (three timing repetitions)

The same 67M uniform/Zipfian inputs and 10M negative queries were used for
`DEFAULT`, `INVERTIBLE`, and `NONE`. The CQF has `qbits=27`, `rbits=9`, and
134,217,728 slots. The uniform distinct-key load is 49.9189%; the Zipf
workload has only 229,118 distinct keys (0.1707% of slots) because of heavy
duplication. The `NONE` mode includes the external SplitMix64 mapping inside
the timed insert/lookup phases.

| Workload | Hash mode | Insert (M/s) | Positive lookup (M/s) | Negative lookup (M/s) | Measured FPR | Expected FPR |
|---|---|---:|---:|---:|---:|---:|
| Uniform | DEFAULT (Murmur64A) | 4.41 | 8.34 | 11.71 | 0.0009692 | 0.0009750 |
| Uniform | INVERTIBLE (`hash_64`) | 4.75 | 8.33 | 13.39 | 0.0009664 | 0.0009750 |
| Uniform | NONE + SplitMix64 | 4.59 | 9.13 | 15.99 | 0.0009787 | 0.0009750 |
| Zipfian | DEFAULT (Murmur64A) | 16.97 | 25.13 | 15.87 | 2.9e-6 | 3.33e-6 |
| Zipfian | INVERTIBLE (`hash_64`) | 19.11 | 36.76 | 20.02 | 3.5e-6 | 3.33e-6 |
| Zipfian | NONE + SplitMix64 | 17.47 | 29.06 | 25.45 | 2.8e-6 | 3.33e-6 |

No hash mode wins every operation. For uniform input, `INVERTIBLE` has the
highest insertion rate, while `NONE` has the highest positive and negative
lookup rates. For Zipfian input, `INVERTIBLE` leads insertion and positive
lookup; `NONE` leads negative lookup. The result supports a workload-sensitive
choice rather than a universal best hash mode. These rates are host-specific
and the 67M hash run is a large-scale extension, not an absolute comparison
with the paper's original hardware.

The 10M-negative-query sample implies approximately 9,750 expected false
positives for uniform input and 33 for Zipf input. The observed counts were
9,692/9,664/9,787 for uniform and 29/35/28 for Zipf (`DEFAULT` /
`INVERTIBLE` / `NONE`). All six measured rates fall within 2.5 binomial
standard deviations of their distinct-key-based expected rates. Timing
repetitions reuse the same negative set, so they measure timing variability
but do not provide three independent FPR samples.

The scale-comparison CSV/chart places these numbers next to the 996k control.
Interpret that comparison carefully: the table geometry changes from
`qbits=20` to `qbits=27`, and uniform CQF load changes from about 95% to 49.9%.
Therefore, throughput changes cannot be attributed to cache size alone.

Deletion is marked `NA` in `hash_modes_67m.csv`; it was not measured in this
hash-mode extension. This is not a claim that CQF lacks deletion. The 996k
hash-mode experiment measures deletion for all three modes, and the separate
cross-filter 67M comparison retains deletion measurements.

## 67M comparison at three FPR targets

For CQF, the workload-specific expected rate is the distinct-key load factor
multiplied by `2^-rbits`, equivalently
`distinct_keys / 2^(qbits+rbits)`. Bloom uses the standard occupancy estimate
`(1 - exp(-k*n/m))^k` with `n` equal to the number of distinct inserted keys,
not the number of repeated insertion operations. Cuckoo's displayed
expectation is the conservative two-candidate/four-slot bound `8 / 2^f` for
its fingerprint width `f`. When Cuckoo fails before accepting the workload,
its aggregated theoretical FPR is `NA` because it has no valid full-load
operating point.

### Uniform measured versus expected FPR

| Target | Filter | Measured | Expected |
|---|---|---:|---:|
| 1/256 | CQF | 0.0019408 | 0.0019500 |
| 1/256 | Cuckoo | 0.0009773 | 0.0019531 |
| 1/256 | Bloom | 0.0039591 | 0.0039063 |
| 1/512 | CQF | 0.0009692 | 0.0009750 |
| 1/512 | Cuckoo | 0.0009718 | 0.0019531 |
| 1/512 | Bloom | 0.0019616 | 0.0019531 |
| 1/1024 | CQF | 0.0004827 | 0.0004875 |
| 1/1024 | Cuckoo | 0.0000609 | 0.0001221 |
| 1/1024 | Bloom | 0.0009826 | 0.0009766 |

### Zipfian measured versus expected FPR

| Target | Filter | Measured | Expected | Status |
|---|---|---:|---:|---|
| 1/256 | CQF | 7.3e-6 | 6.67e-6 | Full workload accepted |
| 1/256 | Cuckoo | 0 | NA | Failed after 24 inserts |
| 1/256 | Bloom | 0 | 9.87e-22 | Full workload accepted |
| 1/512 | CQF | 2.9e-6 | 3.33e-6 | Full workload accepted |
| 1/512 | Cuckoo | 0 | NA | Failed after 24 inserts |
| 1/512 | Bloom | 0 | 2.34e-24 | Full workload accepted |
| 1/1024 | CQF | 1.0e-6 | 1.67e-6 | Full workload accepted |
| 1/1024 | Cuckoo | 0 | NA | Failed after 24 inserts |
| 1/1024 | Bloom | 0 | 5.53e-27 | Full workload accepted |

The zero Bloom FPRs are expected because only 229,118 distinct items are
represented among 67M operations. Cuckoo's zero observed FPR is not evidence
of an effective operating point: it stored only 24 items, so FPR is marked
`NA` in the CSV and charts.

## 67M primary comparison at 1/512 (three timing repetitions)

| Workload | Filter | Insert (M/s) | Positive lookup (M/s) | Negative lookup (M/s) | Delete (M/s) |
|---|---|---:|---:|---:|---:|
| Uniform | CQF | 3.85 | 7.03 | 9.92 | 3.62 |
| Uniform | Cuckoo | 18.15 | 19.22 | 18.76 | 18.58 |
| Uniform | Bloom | 6.61 | 7.44 | 12.30 | — |
| Zipfian | CQF | 16.93 | 23.17 | 13.11 | 12.82 |
| Zipfian | Cuckoo | — | — | — | — (24 accepted) |
| Zipfian | Bloom | 36.94 | 38.43 | 31.09 | — |

Memory at the 67M uniform point is 186.81 MB for CQF, 201.33 MB for Cuckoo,
and 108.74 MB for Bloom. At only 49.9% CQF load, it is smaller than Cuckoo
but larger than Bloom. CQF is slower than Bloom and Cuckoo for all uniform
operations on this host; this experiment does **not** demonstrate a CQF
throughput win at 67M. It does show CQF retaining all duplicate-heavy Zipf
operations while Cuckoo fails after 24 inserts.

## Supplementary near-95%-load point (63,753,420 operations, 1/512)

The near-95% point uses `qbits=26` and 67,108,864 CQF slots. CQF uses
93.44 MB (about 11.73 bits per requested uniform item), versus 100.66 MB for
Cuckoo and 103.47 MB for Bloom. Its uniform measured FPR is 0.0018524 versus
0.0018555 expected. CQF's uniform throughput is lower than at 49.9% load
(insert 3.45M/s, positive lookup 4.90M/s, negative lookup 5.94M/s, delete
2.48M/s), showing the accuracy/space/locality trade-off rather than hiding
it. Under Zipf, CQF again accepts the complete workload and Cuckoo accepts
only 24 operations.

## Overall conclusions and limits

1. The implementation and validation pipeline now tests the requested 67M
   operation scale and all three FPR targets with one shared set of inputs.
2. The expected-versus-measured FPR estimates track closely for CQF and Bloom
   under uniform and Zipf workloads. Bloom's Zipf zero is consistent with
   its extremely small distinct-key-based expectation. Cuckoo Zipf is a
   capacity failure, not an accuracy result.
3. CQF's 95% load can reduce its footprint below Bloom and Cuckoo, but the
   exact 67M power-of-two geometry lands at 49.9%; the supplemental 63.75M
   point demonstrates the near-95% space point. Higher load reduces measured
   FPR's headroom but lowers throughput on this host.
4. We do not observe a CQF uniform-throughput win on this machine at 67M.
   Results are host-specific and should not be represented as a reproduction
   of the paper's absolute throughput numbers. The paper's original hardware,
   multi-threading, SSD, and merge experiments are not part of this phase.
5. The 1/256 and 1/1024 67M FPR-sweep points are single timing passes; the
   1/512 primary paper-scale and the hash-mode study use three timing passes.
   FPRs reuse a fixed 10M negative-query sample across timing repeats, so an
   independent-seed accuracy replication remains a useful next validation.
