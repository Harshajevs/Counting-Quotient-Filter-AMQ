# Phase-2 extended results

All Phase-2 results are stored here; the original Phase-1 `results/bench.csv`
and `results/chart_*.png` are preserved unchanged.

## Included data and plots

- `hash_modes.csv` / `hash_modes_raw.csv`: three CQF hash modes on the 996,148
  operation control workload; three timing repetitions, deletion included,
  and 10M negative queries.
- `hash_modes_67m.csv` / `hash_modes_67m_raw.csv`: the same three CQF hash
  modes at 67M operations; three timing repetitions and 10M negative queries.
  Delete is marked `NA` at this scale for all modes; the study isolates hash
  cost in insert/lookup/FPR paths.
- `hash_scale_comparison.csv` and `hash_scale_comparison_throughput.png`:
  compares the 996k and 67M hash-mode results. CQF geometry changes between
  scales, so it is a scale/configuration comparison, not a cache-only test.
- `paper_scale_1_256.*`, `paper_scale_1_512.*`, `paper_scale_1_1024.*`: 67M
  operation comparisons at three target FPRs. The 1/512 result has three
  timing repetitions; 1/256 and 1/1024 have one each.
- `paper_scale_highload_1_512.*`: supplementary 63,753,420-operation point
  selected to place a 2^26-slot CQF at approximately 95% distinct-key load.
- `scale_comparison.csv` and `scale_comparison_*.png`: Phase-1 cache-sized
  baseline versus the exact 67M run at 1/512.
- `cqf_load_factor_comparison.csv` and `cqf_load_factor_*.png`: CQF capacity
  rounding and throughput/FPR trade-offs between the 67M/50%-load and
  63.75M/95%-load configurations.
- `paper_scale_fpr_sweep_*.png`: comparisons across all three target FPRs.
- `*_configuration.txt`: input distinct counts, table geometry, load factors,
  hash-mode selection, repetition count, and filter sizing used for each run.

`*_raw.csv` retains per-run timings; the non-raw CSVs contain averages. The
three timing repetitions reuse the same deterministic negative-query sample,
so they improve timing stability but do not constitute independent FPR
samples.

The binary input datasets are generated under `*_data/` folders. They are
excluded from the ZIP/Git package because they are large; scripts regenerate
them deterministically when needed.
