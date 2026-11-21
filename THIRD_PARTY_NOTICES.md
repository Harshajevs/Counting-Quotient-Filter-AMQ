# Third-party notices

The existing CQF and Cuckoo filter reference code retains its upstream license
and attribution files. The Bloom filter baseline retains its original source
attribution in the repository.

The new Counting Bloom, Blocked Bloom, XOR and Binary Fuse-style implementations
in `filters/amq_extra.hpp` are original scalar reference implementations written
for this benchmark. Their algorithmic designs are informed by the published
papers listed in `FILTER_CATALOG.md`; no third-party SIMD implementation source
is copied into this file.

The project is a research/benchmark prototype. The new filters should not be
presented as optimized or bit-for-bit replications of the paper authors'
reference implementations.
