# Phase 3 — expanded AMQ comparison: implementation and validation status

> Historical status from the supplied Phase-3 archive. The new report runs
> subsequently completed all seven families at 67M operations, the 67M hash
> study and supplementary capacity/error-target controls. See the root README,
> `results/report/COMPLETED.txt` and the `*report*` result files for that evidence.

## Implemented filter families

The current benchmark contains seven filter families:

1. Counting Quotient Filter (CQF)
2. Cuckoo filter
3. Standard Bloom filter
4. Counting Bloom filter (packed 4-bit counters with exact overflow side table)
5. Blocked Bloom filter (512-bit blocks)
6. XOR filter (static, immutable)
7. Binary Fuse-style scalar filter (static, immutable)

The four new filters are implemented in `filters/amq_extra.hpp` and driven by
`filters/bench_extra_filters.cpp`. They are scalar C++ reference
implementations built for a shared reproducible experiment. The Binary Fuse
implementation is explicitly a *style/reference implementation*, not a
bit-for-bit reproduction of the authors' optimized code. The XOR and Binary
Fuse filters are immutable: no online insertion or deletion rate is claimed.
Their deduplication/preparation time, build time, build latency, positive and
negative query rates, memory and FPR are reported separately.

## Completed experiments included in this package

### Primary seven-filter comparison

- Workload: 1,000,000 insertion operations per distribution.
- Distributions: uniform and Zipfian (finite universe 201,000,000; exponent
  1.5; deterministic input seed).
- CQF capacity rounding: the requested-operation capacity rule selects
  `qbits=21` / 2,097,152 slots at exactly 1M, which is about 47.68% distinct
  load for uniform input. This differs from the Phase-1 996,148-operation
  control, which fits 2^20 slots at about 95% load.
- Target FPR: 1/512.
- Timing repetitions: three per filter and distribution.
- Negative queries: 1,000,000 per distribution.
- Main combined result: `all_filters_expanded_phase3_1m_1_512_v2.csv` (14 rows).
- Added-filter raw results: `additional_filters_expanded_phase3_1m_1_512_v2_raw.csv`
  (24 rows: four filters × two distributions × three repeats).
- Added-filter aggregate: `additional_filters_expanded_phase3_1m_1_512_v2.csv`
  (eight rows).
- Ten unified plots are included with the same `_v2` tag.

### Three-target smoke/validation runs

The new filter family was also run and verified on 100,000 operations at each
of 1/256, 1/512 and 1/1024, one timing repetition per filter/distribution.
These smaller runs check FPR-target parameterization and output handling; they
are not a substitute for repeated large-sample publication measurements.
Their tags are `phase3_validation_fpr_1_256`,
`phase3_validation_fpr2_1_512` and `phase3_validation_fpr2_1_1024`.

### Preserved Phase-2 results

All existing Phase-1 baseline outputs and Phase-2 results (including the
67-million CQF/Cuckoo/Bloom comparison, the three FPR targets, the CQF
hash-mode study and the near-95%-load companion) are retained. They were not
replaced with the new seven-filter experiment.

**Scope boundary:** the new four filter implementations have been fully
benchmarked at 1M in this package. A new all-seven-family 67M run has not been
completed here. The 67M results that are already present in the package are
from the previous three-filter Phase-2 comparison and must not be described as
67M measurements of Counting Bloom, Blocked Bloom, XOR or Binary Fuse-style.
The seven-filter runner is provided for larger follow-up runs after a staged
resource test.

## Selected observations from the 1M uniform comparison

The following are host-specific means from the included three-repeat result.
Rates are millions of operations (or distinct keys built for static filters)
per second; memory is decimal MB.

| Filter | Insert / build (M/s) | Positive lookup (M/s) | Negative lookup (M/s) | Delete (M/s) | Memory (MB) | Measured FPR |
|---|---:|---:|---:|---:|---:|---:|
| CQF | 15.21 | 27.30 | 40.19 | 12.88 | 2.937 | 0.000952 |
| Cuckoo | 25.35 | 132.37 | 128.75 | 50.35 | 1.573 | 0.001799 |
| Bloom | 40.45 | 50.26 | 30.86 | N/A | 1.623 | 0.001907 |
| Counting Bloom | 11.12 | 22.70 | 32.73 | 16.31 | 6.492 | 0.001984 |
| Blocked Bloom | 38.73 | 37.29 | 51.20 | N/A | 1.948 | 0.000955 |
| XOR (static build) | 13.95 | 68.68 | 69.55 | N/A | 1.384 | 0.001942 |
| Binary Fuse-style (static build) | 17.28 | 63.83 | 65.28 | N/A | 1.413 | 0.000985 |

This snapshot illustrates why the comparison is capability- and workload-
dependent rather than a single winner ranking:

- Standard Bloom is the fastest online inserter among the dynamic filters in
  this particular uniform run, while providing no deletion.
- Cuckoo has very high query and deletion throughput on uniform data, but its
  duplicate-heavy Zipfian run fails after accepting only 24 insertions; its
  partial-run query/FPR rates are therefore marked `NA` in the unified table.
- Counting Bloom adds one-at-a-time deletion, with substantially higher memory
  and lower throughput than standard Bloom in this configuration.
- Blocked Bloom is competitive on insertion and has the highest negative
  lookup throughput among the two newly introduced dynamic filters in this
  uniform run; Cuckoo remains substantially faster on uniform lookups. It has
  no delete.
- XOR and Binary Fuse-style provide high query throughput and compact static
  representations. Their build rates are *distinct-key construction rates*,
  not online insertion rates; neither supports incremental updates/deletion.
- CQF retains counting and deletion functionality and fully handles the
  duplicate-heavy workload, but has a larger uniform footprint in this exact
  1M configuration.

On Zipfian data, the distinct-key cardinality is much smaller than the number
of operations. That makes membership-only Bloom and static filters compact;
Counting Bloom still maintains occurrence counts. The CQF benchmark reserves
capacity using requested operations to accommodate its embedded-counter
representation. Consequently, memory comparisons must always be read with the
`n_distinct`, `n_requested` and `config_param` columns, not as though every
filter had identical capacity semantics.

## Validation performed

- `scripts/build_all.sh`: all four benchmark executables compiled.
- `scripts/test_all.sh`: existing CQF/Cuckoo/Bloom regressions and the new
  Counting Bloom, Blocked Bloom, XOR and Binary Fuse-style tests passed.
- Additional-filter test compiled and passed under AddressSanitizer and
  UndefinedBehaviorSanitizer.
- `python3 -m py_compile scripts/*.py data/generate_data.py`: passed.
- `bash -n scripts/*.sh`: passed.
- `verify_all_filters.py` passed for the 1M/three-repeat primary result and
  for the three 100k FPR-target checks.
- Positive lookup verification passed for accepted filters. Counting Bloom
  deletion removed all requested occurrences. Unsupported operations for
  immutable/static filters and non-deleting filters are recorded as `NA`.
- The XOR fingerprint path uses a separate avalanche step; the final `_v2`
  main result was generated after that correction.

## Measurement limitations and publication checklist

1. **Host dependence:** the available test host is an x86-64 AMD EPYC 9V74
   Linux environment with five visible CPU cores and a 32 MiB L3 cache. The
   numbers are not directly comparable to published results collected on
   other hardware.
2. **Scalar implementations:** the new implementations are reference
   implementations, not tuned SIMD or authors' optimized implementations.
   The Binary Fuse-style implementation is not claimed to reproduce the exact
   optimized Binary Fuse code.
3. **Latency definition:** reported ns/op is batch elapsed time divided by
   operation count. It is a mean batch-derived latency, not a distribution of
   per-operation samples; p50/p95/p99 latency is not measured.
4. **FPR sample:** negative inputs are deterministic and reused across timing
   repeats. Timing repeats measure timing variability, not independent FPR
   sampling. Publication-quality accuracy evaluation should use multiple
   independent negative-query seeds and confidence intervals.
5. **Peak memory:** `memory_bytes` describes the filter footprint (and a
   documented estimate for the Counting Bloom overflow side table); it does
   not include every temporary allocation during static filter construction.
6. **Large scale:** the new four filters are tested here at 1M, while the
   inherited Phase-2 67M rows cover only CQF, Cuckoo and standard Bloom. Before
   publishing a 67M seven-family claim, run `run_filter_expansion.sh` for all
   seven families at that scale and preserve its raw per-repeat data.
7. **Recommended next experiments:** 5M/10M seven-family scale checks, 67M
   seven-family when memory allows, multiple independent FPR seeds, and
   separately optimized/reference-source implementations (especially Binary
   Fuse) with compiler flags and version pinned.

## Research context and next candidates

The SPAA 2023 Workshop on Filter Data Structures lists Binary Fuse,
InfiniFilter, Maplets, adaptive filters and GPU-oriented filters among its
agenda topics. Candidate follow-up families are documented in
`FILTER_CATALOG.md`:

- InfiniFilter: expandable dynamic filter; evaluate growth/expansion cost,
  remapping, and query/delete behaviour across capacity changes.
- Maplets: evaluate in the key-value-store compaction context in which the
  structure is proposed, not as a simplistic drop-in standalone filter.
- Adaptive Quotient Filters: measure adaptation after observed false positives
  under controlled query skew and include adaptation overhead.
- GPU filters: use a GPU-capable host, explicit transfer costs and batch-size
  sweeps; do not mix those results with CPU-only microbenchmarks.

References include the SPAA 2023 workshop page, InfiniFilter (SIGMOD 2023,
DOI 10.1145/3589285), Maplets (SIGMOD 2023, DOI 10.1145/3588726), and Adaptive
Quotient Filters (SIGMOD 2025, DOI 10.1145/3677128). Full references and the
implemented algorithms' papers are in `FILTER_CATALOG.md`.
