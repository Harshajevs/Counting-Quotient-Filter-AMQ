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


def gen_negative_keys(n_neg: int, positive_keys: np.ndarray, seed: int) -> np.ndarray:
    """Generate negatives disjoint from positives using vectorized binary search.

    Unlike a Python set, this remains practical for tens of millions of keys.
    """
    rng = np.random.default_rng(seed)
    sorted_positive = np.sort(positive_keys)
    out = []
    remaining = n_neg
    while remaining:
        batch = rng.integers(1, UINT64_MAX, size=max(remaining * 2, 4096), dtype=np.uint64)
        idx = np.searchsorted(sorted_positive, batch)
        valid = idx >= sorted_positive.size
        in_range = ~valid
        valid[in_range] = sorted_positive[idx[in_range]] != batch[in_range]
        accepted = batch[valid]
        if accepted.size:
            take = min(remaining, accepted.size)
            out.append(accepted[:take])
            remaining -= take
    return np.concatenate(out).astype(np.uint64, copy=False)


def write_keys(path: str, keys: np.ndarray) -> None:
    if path.endswith(".bin"):
        # Native little-endian uint64 stream; C/C++ drivers mmap/read it fast.
        np.asarray(keys, dtype=np.uint64).tofile(path)
        return
    # Text remains supported for backwards compatibility.
    with open(path, "w", encoding="utf-8") as f:
        chunk = 250_000
        for start in range(0, len(keys), chunk):
            part = keys[start:start + chunk]
            f.write("\n".join(str(int(k)) for k in part))
            f.write("\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--n", type=int, default=1_000_000)
    ap.add_argument("--universe", type=int, default=PAPER_ZIPF_UNIVERSE)
    ap.add_argument("--skew", type=float, default=1.5)
    ap.add_argument("--neg", type=int, default=100_000)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--binary", action="store_true", help="write raw uint64 .bin files")
    args = ap.parse_args()
    if args.n <= 0 or args.neg <= 0 or args.universe <= 0 or args.skew <= 1.0:
        raise SystemExit("n, neg, universe must be positive and skew must exceed 1")
    os.makedirs(args.outdir, exist_ok=True)
    ext = "bin" if args.binary else "txt"
    chunk = 1_000_000

    # Uniform stream: full-width 64-bit values, matching the paper's input
    # representation. Independent negative draws have negligible overlap
    # probability at this workload size.
    print(f"Generating {args.n} uniform keys in chunks...")
    rng_u = np.random.default_rng(args.seed)
    with open(os.path.join(args.outdir, f"uniform_positive.{ext}"), "wb" if args.binary else "w") as f:
        for start in range(0, args.n, chunk):
            count = min(chunk, args.n-start)
            vals = rng_u.integers(1, np.uint64(1 << 63), size=count, dtype=np.uint64)
            if args.binary: vals.tofile(f)
            else: f.write("\n".join(map(str, vals.tolist()))+"\n")
    uniform_distinct = args.n  # 64-bit birthday collision probability is negligible at this scale.
    rng_neg = np.random.default_rng(args.seed+1)
    with open(os.path.join(args.outdir, f"uniform_negative.{ext}"), "wb" if args.binary else "w") as f:
        left=args.neg
        while left:
            count=min(left,chunk)
            vals=rng_neg.integers(1, UINT64_MAX, size=count, dtype=np.uint64)
            if args.binary: vals.tofile(f)
            else: f.write("\n".join(map(str, vals.tolist()))+"\n")
            left-=count

    # Zipf stream: keep only a compact dictionary of distinct ranks/counts,
    # rather than materialising 67M Python integers or a giant NumPy sort.
    print(f"Generating {args.n} Zipf keys in chunks (universe={args.universe}, skew={args.skew})...")
    rng_z=np.random.default_rng(args.seed)
    rank_counts={}
    with open(os.path.join(args.outdir, f"zipf_positive.{ext}"), "wb" if args.binary else "w") as f:
        remaining=args.n
        while remaining:
            count=min(chunk,remaining)
            ranks=sample_zipf_bounded(rng_z,count,args.universe,args.skew)
            keys=splitmix64(ranks,args.seed)
            keys=np.where(keys==0,np.uint64(1),keys).astype(np.uint64,copy=False)
            if args.binary: keys.tofile(f)
            else: f.write("\n".join(map(str, keys.tolist()))+"\n")
            u,c=np.unique(ranks,return_counts=True)
            for rank,freq in zip(u.tolist(),c.tolist()): rank_counts[rank]=rank_counts.get(rank,0)+freq
            remaining-=count
    zipf_distinct=len(rank_counts)
    zipf_max_frequency=max(rank_counts.values()) if rank_counts else 0
    zipf_key_set=set(int(splitmix64(np.asarray([r],dtype=np.uint64),args.seed)[0]) for r in rank_counts)
    rng_neg=np.random.default_rng(args.seed+101)
    with open(os.path.join(args.outdir, f"zipf_negative.{ext}"), "wb" if args.binary else "w") as f:
        written=0
        while written<args.neg:
            vals=rng_neg.integers(1,UINT64_MAX,size=max(4096,min(chunk,(args.neg-written)*2)),dtype=np.uint64)
            accepted=[int(v) for v in vals if int(v) not in zipf_key_set]
            take=accepted[:args.neg-written]
            if take:
                arr=np.asarray(take,dtype=np.uint64)
                if args.binary: arr.tofile(f)
                else: f.write("\n".join(map(str,take))+"\n")
                written+=len(take)

    manifest={"n":args.n,"universe":args.universe,"skew":args.skew,"neg":args.neg,
              "seed":args.seed,"uniform_distinct_keys":uniform_distinct,
              "zipf_distinct_keys":zipf_distinct,"zipf_max_frequency":zipf_max_frequency,
              "uniform_distinct_note":"N assumed; 64-bit birthday collision probability is negligible at this scale"}
    with open(os.path.join(args.outdir,"manifest.txt"),"w",encoding="utf-8") as f:
        for key,value in manifest.items(): f.write(f"{key}={value}\n")
    print("Done. Files written to:",args.outdir)
    print(f"  uniform distinct ~= {uniform_distinct:,}")
    print(f"  zipf distinct     = {zipf_distinct:,}")

if __name__ == "__main__":
    main()
