#!/usr/bin/env python3
"""
generate_data.py — generate the shared inputs used by all three AMQ filters.

The research paper uses pre-generated 64-bit hash values and evaluates both
uniform-random and Zipfian workloads (Zipf coefficient 1.5).  This generator
keeps a single shared set of keys for Bloom, Cuckoo and CQF so that the filter
implementations themselves, rather than different input data, determine the
benchmark differences.

The Zipfian sampler uses NumPy's fast discrete Zipf sampler and rejects the
rare samples above the finite universe bound.  This avoids constructing a
massive probability/CDF array when using the paper's ~201-million-key
universe.

Output format: one unsigned 64-bit integer per line.
"""
import argparse
import os
from typing import Set

import numpy as np

UINT64_MAX = np.iinfo(np.uint64).max
PAPER_ZIPF_UNIVERSE = 201_000_000


def splitmix64(x: np.ndarray, seed: int) -> np.ndarray:
    """Mix small rank values into well-spread 64-bit keys."""
    x = (x.astype(np.uint64) + np.uint64(seed) + np.uint64(0x9E3779B97F4A7C15))
    x = (x ^ (x >> np.uint64(30))) * np.uint64(0xBF58476D1CE4E5B9)
    x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94D049BB133111EB)
    return x ^ (x >> np.uint64(31))


def gen_uniform_keys(n: int, seed: int) -> np.ndarray:
    """Generate n 64-bit keys; replace the reserved zero key if sampled."""
    rng = np.random.default_rng(seed)
    keys = rng.integers(1, UINT64_MAX, size=n, dtype=np.uint64)
    return np.where(keys == 0, np.uint64(1), keys)


def sample_zipf_bounded(rng: np.random.Generator,
                        n: int,
                        universe: int,
                        skew: float) -> np.ndarray:
    """Draw n ranks from a finite Zipf-like universe efficiently.

    NumPy's zipf() samples the standard unbounded Zipf distribution.  For the
    large universe used by the paper, the rejected tail above 201M is tiny.
    Rejection keeps the resulting samples on ranks [1, universe], while
    avoiding an O(universe) CDF allocation.
    """
    if universe <= 0:
        raise ValueError("universe must be positive")
    if skew <= 1.0:
        raise ValueError("skew must be > 1 for the rejection-based Zipf sampler")

    chunks = []
    remaining = n
    while remaining:
        # A small safety margin avoids too many refill iterations.  For the
        # default paper parameters the rejection rate is extremely small.
        draw_count = max(remaining, int(remaining * 1.02) + 16)
        draws = rng.zipf(skew, size=draw_count)
        accepted = draws[draws <= universe]
        if accepted.size:
            take = min(remaining, accepted.size)
            chunks.append(accepted[:take])
            remaining -= take

    ranks = np.concatenate(chunks) if chunks else np.empty(0, dtype=np.int64)
    return ranks.astype(np.uint64) - np.uint64(1)


def gen_zipfian_keys(n: int, universe: int, skew: float, seed: int) -> np.ndarray:
    """Generate repeated 64-bit keys following a Zipfian rank distribution."""
    rng = np.random.default_rng(seed)
    rank_idx = sample_zipf_bounded(rng, n, universe, skew)
    keys = splitmix64(rank_idx, seed)
    return np.where(keys == 0, np.uint64(1), keys)


def gen_negative_keys(n_neg: int, positive_set: Set[int], seed: int) -> np.ndarray:
    """Generate n_neg keys guaranteed not to occur in positive_set."""
    rng = np.random.default_rng(seed)
    out = []
    while len(out) < n_neg:
        batch = rng.integers(1, UINT64_MAX, size=max(n_neg - len(out), 4096), dtype=np.uint64)
        for value in batch:
            k = int(value)
            if k not in positive_set:
                out.append(k)
                if len(out) == n_neg:
                    break
    return np.asarray(out, dtype=np.uint64)


def write_keys(path: str, keys: np.ndarray) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(str(int(k)) for k in keys))
        f.write("\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--n", type=int, default=1_000_000,
                    help="number of insert operations in each positive workload")
    ap.add_argument("--universe", type=int, default=PAPER_ZIPF_UNIVERSE,
                    help="finite Zipfian universe (paper uses about 201 million)")
    ap.add_argument("--skew", type=float, default=1.5,
                    help="Zipfian coefficient (paper uses 1.5)")
    ap.add_argument("--neg", type=int, default=100_000,
                    help="number of independent negative queries")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if args.n <= 0 or args.neg <= 0:
        raise SystemExit("--n and --neg must be positive")
    if args.universe <= 0:
        raise SystemExit("--universe must be positive")

    os.makedirs(args.outdir, exist_ok=True)

    print(f"Generating {args.n} uniform-random 64-bit keys (seed={args.seed})...")
    uniform = gen_uniform_keys(args.n, args.seed)
    write_keys(os.path.join(args.outdir, "uniform_positive.txt"), uniform)

    print(f"Generating {args.n} Zipfian keys (universe={args.universe}, skew={args.skew})...")
    zipf = gen_zipfian_keys(args.n, args.universe, args.skew, args.seed)
    write_keys(os.path.join(args.outdir, "zipf_positive.txt"), zipf)

    print(f"Generating {args.neg} independent negative keys for each workload...")
    uniform_set = {int(k) for k in uniform}
    zipf_set = {int(k) for k in zipf}
    uniform_neg = gen_negative_keys(args.neg, uniform_set, args.seed + 1)
    zipf_neg = gen_negative_keys(args.neg, zipf_set, args.seed + 101)
    write_keys(os.path.join(args.outdir, "uniform_negative.txt"), uniform_neg)
    write_keys(os.path.join(args.outdir, "zipf_negative.txt"), zipf_neg)

    zipf_max_frequency = 0
    if zipf.size:
        _, zipf_counts = np.unique(zipf, return_counts=True)
        zipf_max_frequency = int(zipf_counts.max())

    manifest = {
        "n": args.n,
        "universe": args.universe,
        "skew": args.skew,
        "neg": args.neg,
        "seed": args.seed,
        "uniform_distinct_keys": len(uniform_set),
        "zipf_distinct_keys": len(zipf_set),
        "zipf_max_frequency": zipf_max_frequency,
    }
    with open(os.path.join(args.outdir, "manifest.txt"), "w", encoding="utf-8") as f:
        for key, value in manifest.items():
            f.write(f"{key}={value}\n")

    print("Done. Files written to:", args.outdir)
    print(f"  uniform distinct = {len(uniform_set):,}")
    print(f"  zipf distinct    = {len(zipf_set):,}")


if __name__ == "__main__":
    main()
