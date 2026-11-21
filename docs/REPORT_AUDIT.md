# Research-report audit (21 November 2026)

This audit records the report-generation snapshot before its later repository
publication. Public GitHub head checked during preparation:
fe184baa6933d7ac3bf3fc18bf2a2245c8b73e00. The API returned no public pull-request
entries at that time. The supplied ZIP contains the seven-filter extension
beyond that head. No remote writes were made during report preparation.

The repository edition includes the final paper and its editable sources under
`report/`. The source/data manifests retain the delivered benchmark snapshot;
publication also preserves the existing upstream NA-safe plot parser and adds
README links and ignore rules for generated files. `source_manifest.json`
hashes the published benchmark source; `source_manifest_report_delivery.json`
preserves the earlier delivered package manifest. Measured results are unchanged.

Changes for the report:
- Added exact binary-workload auditing (scripts/audit_workloads.py), with tests
  for duplicates, true members in negatives, and valid duplicate-heavy streams.
  Paper-scale and hash runners call it outside filter timing; audit.json records
  exact cardinality, maximum frequency, zero overlap and SHA-256 hashes.
- Added CQF geometry counters to stderr, outside timed batches. Occupied slots
  and stored fingerprints are distinguished from original distinct keys.
- Restored the upstream CQF and Cuckoo LICENSE files missing from the ZIP.
- Added report experiment orchestration and data-to-figure/table regeneration.
  Supplementary-run checks reject partial insertions and stale appended rows;
  reruns clear old supplementary CSVs and the previous completion marker.
- Report asset generation masks the legacy Bloom deletion zero as unsupported,
  with a regression test preventing fictitious zero-throughput measurements.
- Corrected the plot label to final filter footprint and documented the 63-bit
  uniform-positive value domain.

Artifact integrity:
- The revised 20-page report adds a detailed target-sweep table and a labelled
  query-only mix model generated from mean measured batch costs. These are
  calculations from existing raw data, not new timing runs. The mix generator
  masks incomplete workloads; its formula and endpoint behaviour were checked.
- `results/report/source_manifest.json` hashes the final packaged source files.
  `source_manifest_run_start.json` preserves the earlier execution snapshot;
  later changes add report tooling/tests and correct labels/comments. The latter
  is historical evidence, not a checksum list for the final package.
- The main report CSVs have complete validated repetition counts. A recovery
  invocation restored the original-three-filter 67M rows after an orchestration
  script was inadvertently edited during execution; the completed added-filter
  rows were preserved. Final figures use the restored, validated raw data.
- `INPUT_PROVENANCE.txt` records the supplied archive checksum and public-head
  check. The final functional-test log is from a fresh post-run check.

Interpretation constraints:
- CQF default uses MurmurHash64A; invertible is the reference width-limited
  Thomas Wang mixer; none receives an externally computed SplitMix64-style
  mapping within each timed loop. These are existing algorithms, not a newly
  invented hash function. None does not mean zero hashing cost. The default
  path also includes runtime reduction by a 128-bit range, while the external
  path masks directly; gains are not standalone mixer-cost measurements.
- Uniform generation initially assumes distinctness and independent negatives.
  The added exact audit now verifies both before accepting a reported run.
- The main CQF/Cuckoo capacity basis is requested operations; the Bloom family
  and static filters use exact distinct cardinality as offline sizing knowledge.
  CQF Zipf memory under this rule is intentionally conservative.
- Cuckoo's multiply-shift hash coefficients come from std::random_device each
  process. They are not captured in the historical driver. Timing repeat
  variation therefore includes hash variation, and measured FPR can vary.
- Static construction includes separate preprocessing and build timings; online
  insertion/deletion are unsupported. Reported filter memory excludes input
  arrays, graph workspaces, allocator overhead (except the CBF estimate), RSS,
  and whole-process peak memory. It is not a construction-memory measurement.
- Mean throughput and mean batch-derived latency are not exact reciprocals when
  per-repeat duration varies. No tail-latency claims are justified.
- Repeating the same negative stream does not multiply the independent query
  sample size. Wilson intervals use 10M queries per run, with Cuckoo displayed
  separately for its changing hash realization.
- The Binary Fuse-style scalar variant adds a guard fingerprint bit; comparisons
  against XOR are not matched at identical achieved FPR. Its implementation is
  not the optimized published Binary Fuse code.
- New measurements use linux/amd64 Ubuntu 22.04 via Rosetta on Apple M2. Virtual
  CPUID/cache reports must not be mistaken for a physical Intel machine.
