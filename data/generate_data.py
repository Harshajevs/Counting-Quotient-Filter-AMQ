#!/usr/bin/env python3
"""
generate_data.py — build the shared input files used by every filter's benchmark.

Every filter (Bloom, cuckoo, CQF) is benchmarked on the exact same key files,
so the comparison is apples-to-apples. This script produces, for both a
uniform-random workload and a skewed (Zipfian) workload:

  - a "positive" file: the keys that get inserted into the filter
  - a "negative" file: keys guaranteed NOT to be inserted, used to measure
    the actual false-positive rate against the theoretical one

Output format: one 64-bit unsigned decimal integer per line (same format the
existing CQF/cuckoo test drivers already expect).

Usage:
    python3 generate_data.py --outdir ../results/data \
        --n 1000000 --universe 200000 --skew 1.5 --neg 100000 --seed 42
"""
import argparse
import os
import numpy as np


def splitmix64(x: np.ndarray, seed: int) -> np.ndarray:
    """Cheap, fast 64-bit mixer used to turn small Zipfian ranks into
    well-spread 64-bit keys (so filters see realistic, hash-like keys
    rather than small consecutive integers)."""
    x = (x.astype(np.uint64) + np.uint64(seed) + np.uint64(0x9E3779B97F4A7C15))
    x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    x = x ^ (x >> np.uint64(31))
    return x


def gen_uniform_keys(n: int, seed: int) -> np.ndarray:
    """n distinct-ish 64-bit random keys. Collisions in a 64-bit space at
    this scale are astronomically unlikely, so no explicit dedup needed."""
    rng = np.random.default_rng(seed)
    # avoid 0 as a key (used as a sentinel/sanity value in some filter tests)
    keys = rng.integers(low=1, high=2**63 - 1, size=n, dtype=np.int64).astype(np.uint64)
    return keys


def gen_zipfian_keys(n: int, universe: int, skew: float, seed: int) -> np.ndarray:
    """n samples drawn from a Zipfian distribution over `universe` distinct
    ranks (rank 1 is the most frequent), then each rank is mapped to a
    well-spread 64-bit key via splitmix64 so repeated draws of the same
    rank repeatedly hit the same 64-bit key (needed so CQF's counting
    behaviour is actually exercised)."""
    ranks = np.arange(1, universe + 1, dtype=np.float64)
    weights = ranks ** (-skew)
    probs = weights / weights.sum()
    cdf = np.cumsum(probs)

    rng = np.random.default_rng(seed)
    draws = rng.random(n)
    rank_idx = np.searchsorted(cdf, draws, side="right")  # 0-indexed rank
    rank_idx = np.clip(rank_idx, 0, universe - 1).astype(np.uint64)

    keys = splitmix64(rank_idx, seed)
    keys = np.where(keys == 0, np.uint64(1), keys)  # avoid the 0 sentinel
    return keys


def gen_negative_keys(n_neg: int, positive_set: set, seed: int) -> np.ndarray:
    """n_neg keys guaranteed to not be in `positive_set`."""
    rng = np.random.default_rng(seed + 1)
    out = []
    # oversample, then filter, then top up if needed — fast in practice
    # since positive_set is a tiny fraction of the 64-bit space
    while len(out) < n_neg:
        batch = rng.integers(low=1, high=2**63 - 1, size=n_neg, dtype=np.int64).astype(np.uint64)
        for k in batch:
            k = int(k)
            if k not in positive_set:
                out.append(k)
                if len(out) >= n_neg:
                    break
    return np.array(out, dtype=np.uint64)


def write_keys(path: str, keys: np.ndarray) -> None:
    with open(path, "w") as f:
        f.write("\n".join(str(int(k)) for k in keys))
        f.write("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True, help="directory to write the .txt files into")
    ap.add_argument("--n", type=int, default=1_000_000, help="number of positive (inserted) keys")
    ap.add_argument("--universe", type=int, default=200_000, help="distinct-item universe for the Zipfian workload")
    ap.add_argument("--skew", type=float, default=1.5, help="Zipfian skew parameter s (paper uses 1.5)")
    ap.add_argument("--neg", type=int, default=100_000, help="number of negative (not-inserted) keys, for FP testing")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)

    print(f"Generating {args.n} uniform-random keys (seed={args.seed})...")
    uni_keys = gen_uniform_keys(args.n, args.seed)
    write_keys(os.path.join(args.outdir, "uniform_positive.txt"), uni_keys)

    print(f"Generating {args.n} Zipfian keys (universe={args.universe}, skew={args.skew})...")
    zipf_keys = gen_zipfian_keys(args.n, args.universe, args.skew, args.seed)
    write_keys(os.path.join(args.outdir, "zipf_positive.txt"), zipf_keys)

    print(f"Generating {args.neg} negative keys for each workload...")
    uni_set = set(int(k) for k in uni_keys)
    zipf_set = set(int(k) for k in zipf_keys)

    uni_neg = gen_negative_keys(args.neg, uni_set, args.seed)
    write_keys(os.path.join(args.outdir, "uniform_negative.txt"), uni_neg)

    zipf_neg = gen_negative_keys(args.neg, zipf_set, args.seed + 100)
    write_keys(os.path.join(args.outdir, "zipf_negative.txt"), zipf_neg)

    # small manifest for reproducibility / to stamp into result CSVs
    with open(os.path.join(args.outdir, "manifest.txt"), "w") as f:
        f.write(f"n={args.n}\n")
        f.write(f"universe={args.universe}\n")
        f.write(f"skew={args.skew}\n")
        f.write(f"neg={args.neg}\n")
        f.write(f"seed={args.seed}\n")
        f.write(f"uniform_distinct_keys={len(uni_set)}\n")
        f.write(f"zipf_distinct_keys={len(zipf_set)}\n")

    print("Done. Files written to:", args.outdir)


if __name__ == "__main__":
    main()
