"""The Figure 5 inflation-level sweep, Section 7.3.

Draws (eps, alpha, delta) uniformly from the evaluated ranges and keeps every
draw. Coverage target: at least TARGET samples in every 0.1%-wide inflation
level of [0, 6.5%). Levels random draws cannot reach are refilled by jittering
the parameters of samples in nearby levels. Levels that two consecutive jitter
rounds fail to grow are declared unreachable and dropped from the target set.

Output: data/random_q20_*.csv, one row per configuration, carrying
(eps, alpha, delta, inflation_pct, bin0..bin99) over the 50,000 measured blocks.
The histogram resolution matches the mapping of Appendix C.1, one hundred bins
of width 0.01.
"""
import csv
import glob
import pathlib
import subprocess

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
ARTIFACT_ROOT = next(p for p in HERE.parents if (p / "build.sh").is_file())
S = str(HERE / "data")
BINARY = str(ARTIFACT_ROOT / "bin" / "random-sample")
BINS = 100                  # the mapping resolution of Appendix C.1
LEVELS = range(65)          # 0.0% .. 6.4%
TARGET = 100
FIRST_BATCH = 20_000
EPS = (0.0, 16.0)
ALPHA = (0.01, 0.99)
DELTA = (0.001, 0.125)


def read_samples():
    rows = []
    for path in sorted(glob.glob(f"{S}/random_q20_*.csv")):
        with open(path) as f:
            rows += [(float(r["eps"]), float(r["alpha"]), float(r["delta"]),
                      float(r["inflation_pct"])) for r in csv.DictReader(f)]
    return rows


def counts_by_level(rows):
    counts = {level: 0 for level in LEVELS}
    for _, _, _, inflation in rows:
        level = int(inflation * 10)
        if inflation >= 0 and level in counts:
            counts[level] += 1
    return counts


def run_batch(tag, params=None, n_uniform=None, seed=0):
    out = f"{S}/random_q20_{tag}.csv"
    if params is not None:
        path = f"{S}/params_{tag}.csv"
        with open(path, "w") as f:
            for eps, alpha, delta in params:
                f.write(f"{eps:.6f},{alpha:.6f},{delta:.6f}\n")
        argv = [BINARY, "-uniform-bins", str(BINS), out, "-file", path]
    else:
        argv = [BINARY, "-uniform-bins", str(BINS), out, str(n_uniform), str(seed)]
    subprocess.run(argv, check=True, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)


def jitter_params(rows, needy, rng):
    params = []
    by_level = {}
    for eps, alpha, delta, inflation in rows:
        by_level.setdefault(int(inflation * 10), []).append((eps, alpha, delta))
    for level, deficit in needy:
        parents = []
        for radius in range(0, 8):
            for near in (level - radius, level + radius):
                parents += by_level.get(near, [])
            if len(parents) >= 10:
                break
        if not parents:
            continue
        for _ in range(deficit * 3):
            eps, alpha, delta = parents[rng.integers(len(parents))]
            params.append((
                float(np.clip(eps + rng.normal(0, 0.4), *EPS)),
                float(np.clip(alpha + rng.normal(0, 0.03), *ALPHA)),
                float(np.clip(delta + rng.normal(0, 0.004), *DELTA)),
            ))
    return params


def main():
    rng = np.random.default_rng(601)
    rows = read_samples()
    if not rows:
        print(f"batch 0: {FIRST_BATCH} uniform draws", flush=True)
        run_batch("000", n_uniform=FIRST_BATCH, seed=601)
        rows = read_samples()

    dead = set()
    stalls = {}
    for iteration in range(1, 30):
        counts = counts_by_level(rows)
        needy = [(lvl, TARGET - counts[lvl]) for lvl in LEVELS
                 if counts[lvl] < TARGET and lvl not in dead]
        filled = sum(1 for lvl in LEVELS if counts[lvl] >= TARGET)
        print(f"iter {iteration}: {filled}/{len(LEVELS)} levels at {TARGET}+, "
              f"{len(rows)} samples, needy {[lvl for lvl, _ in needy]}, "
              f"dead {sorted(dead)}", flush=True)
        if not needy:
            break
        params = jitter_params(rows, needy, rng)
        if not params:
            print("no parents for any needy level, stopping", flush=True)
            break
        run_batch(f"{iteration:03d}", params=params)
        new_rows = read_samples()
        new_counts = counts_by_level(new_rows)
        for lvl, _ in needy:
            if new_counts[lvl] == counts[lvl]:
                stalls[lvl] = stalls.get(lvl, 0) + 1
                if stalls[lvl] >= 2:
                    dead.add(lvl)
            else:
                stalls[lvl] = 0
        rows = new_rows

    counts = counts_by_level(rows)
    print("FINAL:", {lvl: counts[lvl] for lvl in LEVELS}, flush=True)
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
