import csv
from pathlib import Path

def is_na(value):
    return str(value).strip().lower() in {"", "na", "n/a", "nan", "none"}

def read_csv(path):
    with open(path, newline="") as f:
        return list(csv.DictReader(f))

def verify(path, expected_rows, expected_n, skip_delete=False):
    p = Path(path)
    assert p.exists(), f"MISSING FILE: {p}"

    rows = read_csv(p)
    assert len(rows) == expected_rows, (
        f"{p}: expected {expected_rows} rows, found {len(rows)}"
    )

    for r in rows:
        filt = r["filter"]
        dist = r["distribution"]

        n = int(r["n_requested"])
        inserted = int(r["n_inserted"])
        found = int(r["found_positive"])

        assert n == expected_n, f"Unexpected workload size: {p}"
        assert found == inserted, f"Positive lookup mismatch: {p}: {r}"

        if filt in ("cqf", "bloom") or dist == "uniform":
            assert inserted == n, f"Unexpected insertion failure: {p}: {r}"

        if filt == "cuckoo" and dist == "zipfian":
            assert inserted < n, f"Expected duplicate-capacity limitation: {p}"

        theoretical = r.get("theoretical_fp_rate", "")
        if is_na(theoretical):
            assert filt == "cuckoo" and dist == "zipfian", (
                f"Unexpected theoretical FPR N/A: {p}: {r}"
            )

        deleted = r.get("deleted_ok", "")

        if skip_delete:
            assert is_na(deleted), f"Expected skipped deletion: {p}: {r}"
        elif filt == "bloom":
            pass
        elif is_na(deleted):
            assert filt == "cuckoo" and dist == "zipfian" and inserted < n, (
                f"Unexpected unavailable deletion: {p}: {r}"
            )
        else:
            assert int(deleted) == inserted, f"Deletion mismatch: {p}: {r}"

    print(f"PASS: {p} ({expected_rows} rows)")

checks = [
    ("results/bench.csv", 6, 996148, False),
    ("results/bench_raw.csv", 18, 996148, False),

    ("results/extended/hash_modes.csv", 6, 996148, False),
    ("results/extended/hash_modes_raw.csv", 18, 996148, False),

    ("results/extended/hash_modes_67m.csv", 6, 67000000, True),
    ("results/extended/hash_modes_67m_raw.csv", 18, 67000000, True),

    ("results/extended/paper_scale_1_256.csv", 6, 67000000, False),
    ("results/extended/paper_scale_1_256_raw.csv", 6, 67000000, False),

    ("results/extended/paper_scale_1_512.csv", 6, 67000000, False),
    ("results/extended/paper_scale_1_512_raw.csv", 18, 67000000, False),

    ("results/extended/paper_scale_1_1024.csv", 6, 67000000, False),
    ("results/extended/paper_scale_1_1024_raw.csv", 6, 67000000, False),

    ("results/extended/paper_scale_highload_1_512.csv", 6, 63753420, False),
    ("results/extended/paper_scale_highload_1_512_raw.csv", 6, 63753420, False),
]

for args in checks:
    verify(*args)

baseline = list(Path("results").glob("chart_*.png"))
extended = list(Path("results/extended").glob("*.png"))

assert baseline, "No baseline charts found"
assert extended, "No extended charts found"

for p in baseline + extended:
    assert p.stat().st_size > 0, f"Empty plot: {p}"

print()
print(f"Baseline charts: {len(baseline)}")
print(f"Extended charts: {len(extended)}")
print("ALL RESULT AND PLOT CHECKS PASSED.")
