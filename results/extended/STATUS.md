# Phase-2 experiment status

- **Completed:** CQF `DEFAULT`, `INVERTIBLE`, and `NONE` hash-mode comparison
  on the 996,148-operation Phase-1 control workload, uniform and Zipfian,
  10M negative queries and three timing repetitions. Deletion is included.
  `NONE` includes its external SplitMix64 pre-hash in timed loops.
- **Completed:** the same three CQF hash modes on 67M uniform and Zipfian
  operations, with three timing repetitions and 10M negative queries for each
  workload/mode. All 1,206 million positive lookup operations across the 18 raw
  rows were found. Measured FPRs are consistent with the workload-specific
  expectation within binomial sampling variability.
- **Large-scale hash-mode scope:** deletion is explicitly `NA` for the 67M
  hash-mode study. A one-at-a-time deletion attempt was substantially slower
  than the insert/lookup phases and did not complete within the available
  execution window. Deletion remains fully measured in the 996k hash-mode
  control and in the cross-filter 67M comparison; no 67M hash-mode delete rate
  is claimed.
- **Completed:** 67M-operation comparison of CQF, Cuckoo and Bloom under
  uniform and Zipfian input at targets 1/256, 1/512 and 1/1024. The primary
  1/512 result is averaged over three timing repetitions; the other target
  points use one each.
- **Completed:** supplementary 63,753,420-operation 1/512 CQF high-load point
  at approximately 95% occupancy of a 2^26-slot table. This is separately
  named `paper_scale_highload_1_512` and does not overwrite the 67M result.
- **Validated:** full positive lookup counts and deletion counts for each
  supported deletion filter. Cuckoo on Zipf accepted only 24 of 67M requested
  operations; its FPR is reported as `NA` rather than a misleading zero.
- **Validated:** all three FPR targets' measured-vs-theoretical behavior,
  workload-specific distinct-key calculations, aggregate CSVs and plots.
- **Preserved:** `results/bench.csv` and all original Phase-1 charts compare
  byte-for-byte with the uploaded baseline archive.

The measurements are host-specific (AMD EPYC 9V74 Linux x86-64 container;
5 visible CPU cores and 32 MiB L3) and are not a reproduction of the paper's
absolute throughput numbers or hardware. See `EXPERIMENT_NOTES.md` for the
methodology, numerical findings and limitations.
