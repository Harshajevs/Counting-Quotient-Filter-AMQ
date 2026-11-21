# AMQ Filter Catalogue and Benchmark Methodology

The original Phase-3 methodology below is retained for context. The root
README and `docs/REPORT_AUDIT.md` describe the completed 1M/67M report matrix,
source/workload audits and interpretation of the new `*report*` measurements.

This phase broadens the existing CQF/Cuckoo/Bloom benchmark to seven filter
families. The objective is not to declare a universal winner. It is to compare
space, construction/update cost, positive and negative lookup latency, deletion
support, and empirical false-positive behaviour under shared workloads.

## Implemented filter families

| Filter | Class | Online insert | Positive/negative lookup | Delete | Construction model |
|---|---|---:|---:|---:|---|
| Counting Quotient Filter (CQF) | Dynamic, counting | Yes | Yes | Yes | Pre-sized table, online operations |
| Cuckoo filter | Dynamic | Yes | Yes | Yes | Pre-sized table, online operations |
| Standard Bloom filter | Dynamic | Yes | Yes | No | Pre-sized bit array, online operations |
| Counting Bloom filter | Dynamic, counting | Yes | Yes | Yes | Packed 4-bit counters plus overflow side table |
| Blocked Bloom filter | Dynamic, cache-blocked | Yes | Yes | No | 512-bit blocks with block-local bit positions |
| XOR filter | Static, immutable | No | Yes | No | Batch construction from distinct keys |
| Binary Fuse-style filter | Static, immutable | No | Yes | No | Scalar three-segment XOR-peeling construction |

The four new implementations are self-contained scalar C++ reference
implementations in `filters/amq_extra.hpp`; they are not imported SIMD kernels.
The Binary Fuse implementation is a research-oriented scalar variant of the
three-segment fuse construction, not a claim of bit-for-bit reproduction of the
authors' optimized implementation. This distinction matters when comparing
absolute throughput with published results.

### Dynamic filters

- **Counting Bloom:** a conventional counting Bloom layout with packed 4-bit
  counters. Cells that exceed the inline counter range use an exact overflow
  side table, so hot Zipfian keys do not silently saturate. The table supports
  one-occurrence-at-a-time deletion. The overflow table adds memory and hash
  lookup overhead; its memory figure is an estimate of container overhead.
- **Blocked Bloom:** a cache-line-oriented variant using 512-bit blocks and
  independent mixed positions within a selected block. It supports insertion
  and lookup, not deletion. Its allocation includes a 20% guard over the
  conventional Bloom bit budget. Its reported theoretical value is an
  occupancy-conditioned estimate computed from the actual per-block bit
  occupancy, rather than the ordinary global Bloom approximation.

### Static filters

XOR and Binary Fuse are immutable set representations. They are built once from
the exact distinct-key set, then queried. They do not provide incremental
insertion or deletion; those CSV fields are `NA` by design. `preprocess_time_s`
records the copy/dedup preparation step separately from filter construction.
The unified CSV also reports both build-only and end-to-end construction
latency, so static filters are not made to look free by excluding preparation.

The XOR implementation uses a three-partite hypergraph peel. The Binary
Fuse-style implementation uses a three-consecutive-segment fuse graph and
packed fingerprints. Both derive fingerprint bits through a separate
avalanche step and verify that every positive input operation is recognised
after construction. These are scalar reference implementations, not
bit-for-bit reproductions of the authors' optimized implementations.

## Shared benchmark protocol

`run_filter_expansion.sh` orchestrates the original CQF, Cuckoo and Bloom
executables and all four new filters. Every filter receives the same generated
64-bit uniform or Zipfian positive stream and the same independently generated
negative-query stream. The default Zipf setup uses universe 201,000,000 and
skew 1.5. The benchmark records insertion/build, positive lookup, negative
lookup, deletion where supported, memory, false positives, theoretical or
occupancy-conditioned FPR, and repeat identifier.

### Capacity and duplicate semantics

Capacity parameters are recorded in each configuration file:

- CQF and Cuckoo retain the existing benchmark's requested-operation capacity
  basis. CQF's embedded counter representation may consume additional slots
  under repeated-key workloads; using only the distinct count caused the
  reference CQF to exceed its slot bounds in a stress test.
- Bloom, Counting Bloom, Blocked Bloom, XOR and Binary Fuse are sized from the
  exact distinct membership cardinality. Re-inserting a key does not add a new
  set member to these structures. Counting Bloom still increments its counters
  for every occurrence so its multiset/deletion behaviour is exercised.
- The Zipf stream is replayed in full for all online filters. Static filters
  receive the deduplicated set for construction but are queried using the full
  original positive stream. This reflects their immutable set semantics.
- Cuckoo's duplicate-heavy Zipfian insertion can fail early. A partial run is
  labelled `capacity_failure`; its full-workload insertion throughput, FPR,
  positive-query latency on a tiny accepted subset, and deletion throughput
  are reported as `NA` in the unified table. Its accepted count remains visible.

### Latency and throughput

Throughput is measured from a timed batch. Average latency is derived as
`elapsed_time / operation_count` and reported in nanoseconds per operation or
query. These are mean batch-derived latencies, **not** per-operation timestamp
samples and not p50/p95/p99 latency distributions. Static filter construction
reports preprocessing separately, build-only time, and end-to-end time that
includes preparation.

### FPR interpretation

The measured FPR is false positives divided by the number of independent
negative queries. The theoretical estimate is specific to each structure:

- Standard and Counting Bloom use the standard Bloom occupancy formula based
  on distinct keys.
- Blocked Bloom uses its occupancy-conditioned block estimate.
- XOR and Binary Fuse use `2^-fingerprint_bits`; Binary Fuse reserves one guard
  bit beyond `ceil(-log2(target))` in this scalar implementation.
- CQF uses the configured remainder-bit target.
- Cuckoo uses the reference implementation's fingerprint-width estimate only
  when the full workload is accepted. After a capacity failure the operating
  point is not meaningful and is `NA`.

Finite negative-query samples produce statistical variation. A measured rate
slightly above or below its theoretical expectation is not by itself evidence
of a bug; use confidence intervals and repeated seeds/samples for publication.
The current benchmark uses fixed workload seeds to support reproducibility.

## Build, test and run

Inside the repository root, in the supported Ubuntu x86-64 Docker environment:

```bash
./scripts/build_all.sh
./scripts/test_all.sh
```

Run a complete seven-filter comparison at one target:

```bash
./scripts/run_filter_expansion.sh 1000000 1000000 1/512 3 expanded_1_512
```

Run all three FPR targets (1/256, 1/512, 1/1024):

```bash
./scripts/run_filter_expansion_sweep.sh 1000000 1000000 3 expanded
```

A paper-scale run uses substantially more RAM and disk space because the
positive and negative binary inputs are loaded by the benchmark drivers. For
example:

```bash
./scripts/run_filter_expansion.sh 67000000 10000000 1/512 3 expanded_67m_1_512
```

After a run, the key outputs are:

- `results/extended/all_filters_<tag>.csv`: common 14-row table, including
  legacy CQF/Cuckoo/Bloom and the four new filters for two distributions.
- `additional_filters_<tag>_raw.csv`: per-repeat raw rows for new filters.
- `additional_filters_<tag>.csv`: averaged new-filter rows.
- `all_filters_<tag>_*.png`: throughput, average latency, memory, deletion and
  FPR plots.

Verify an experiment with:

```bash
python3 scripts/verify_all_filters.py <tag> <repeats>
```

Generated binary workloads under `results/extended/*_data/` are ignored by
Git; CSVs, configuration files and plots are the shareable experiment outputs.

## Research references

1. P. Pandey, M. A. Bender, R. Johnson, R. Patro. “A General-Purpose Counting
   Filter: Making Every Bit Count.” ACM SIGMOD, 2017. DOI:
   https://doi.org/10.1145/3035918.3035963.
2. T. Mueller Graf and D. Lemire. “Xor Filters: Faster and Smaller Than Bloom
   and Cuckoo Filters.” Journal of Experimental Algorithmics 25, 2020. DOI:
   https://doi.org/10.1145/3376122.
3. T. Mueller Graf and D. Lemire. “Binary Fuse Filters: Fast and Smaller Than
   Xor Filters.” Journal of Experimental Algorithmics 27, 2022. DOI:
   https://doi.org/10.1145/3510449.
4. F. Putze, P. Sanders and J. Singler. “Cache-, Hash- and Space-Efficient
   Bloom Filters.” WEA 2007, pp. 108–121. DOI:
   https://doi.org/10.1007/978-3-540-72845-0_9.
5. F. Bonomi, M. Mitzenmacher, R. Panigrahy, S. Singh and G. Varghese. “An
   Improved Construction for Counting Bloom Filters.” ESA 2006, LNCS 4168,
   pp. 684–695. DOI: https://doi.org/10.1007/11841036_61.
6. P. Pandey. “Workshop on Filter Data Structures (SPAA 2023).”
   https://prashantpandey.github.io/workshop/. The agenda covers Binary Fuse,
   InfiniFilter, Maplets, adaptive filters and GPU-oriented filters.
7. N. Dayan, I. Bercea, P. Reviriego and R. Pagh. “InfiniFilter: Expanding
   Filters to Infinity and Beyond.” Proc. ACM Manag. Data 1(2), 2023. DOI:
   https://doi.org/10.1145/3589285. Its dynamic expansion semantics make it a
   relevant next addition, but expansion/rebuild behaviour requires separate
   metrics beyond a fixed-capacity insert/query benchmark.
8. A. Conway, M. Farach-Colton and R. Johnson. “SplinterDB and Maplets:
   Improving the Tradeoffs in Key-Value Store Compaction Policy.” ACM SIGMOD,
   2023. DOI: https://doi.org/10.1145/3588726. Maplets is connected to
   key-value-store compaction, so a fair evaluation should include that
   surrounding workload rather than treating it as a drop-in standalone AMQ.
9. R. Wen, H. McCoy, D. Tench, G. Tagliavini, M. A. Bender, A. Conway,
   M. Farach-Colton, R. Johnson and P. Pandey. “Adaptive Quotient Filters.”
   ACM SIGMOD, 2025. DOI: https://doi.org/10.1145/3677128. The paper studies
   adaptation in response to false-positive query observations, so a future
   comparison should measure adaptation cost and query-distribution effects.

## Candidate extensions not implemented in this phase

The workshop also identifies InfiniFilter, Maplets, adaptive filters and
GPU-oriented filters as active directions. They are not included in the seven
implemented families for distinct methodological reasons:

- **InfiniFilter** is a strong next candidate for a dynamic AMQ comparison.
  Its expansion policy, fingerprint remapping, resize cost and post-expansion
  query/delete behaviour should be measured explicitly; a fixed-capacity
  runner would miss its principal contribution. The authors' Java reference
  implementation is available at
  https://github.com/nivdayan/FilterLibrary.
- **Maplets** are presented in the context of key-value-store compaction
  policy. A meaningful comparison should model compaction/read/write paths,
  rather than pretend that Maplets is a direct replacement for a standalone
  Bloom membership filter.
- **Adaptive Quotient Filters** change their representation based on observed
  false positives. They warrant query-stream experiments with controlled
  skew, adaptation disabled/enabled phases and an accounting of adaptation
  overhead; a static insert/query benchmark would not capture that behaviour.
- **GPU-oriented filters** need a GPU-capable execution host and batch sizes
  that amortize data transfer. They should be evaluated in a separate CPU/GPU
  benchmark mode rather than mixed into CPU-only latency rankings.

These are scope decisions, not claims that the candidates cannot be compared.
They are natural follow-up phases once the current common CPU benchmark is
stable.
