"""Figures 7 and 8 -- the amplification indicators.

Each point runs one trajectory through `bin/kappa-fees`, which follows the
Section 7.1 protocol and returns the base fee of every chain at every step. The
two kappa definitions are then applied to those fee series.

  kappa_def  is Chain 0's own delayed self-reinforcement. A past deviation
             counts when it carries the same sign as the current one.
  kappa_att  is a peer's delayed force on Chain 0. A past deviation of the peer
             counts when it carries the opposite sign to Chain 0's current one.

Both are reported as the 90th percentile of the per-step series. The ratio
divides by the current deviation, which crosses zero every time the trajectory
passes through equilibrium, so the mean and the maximum are dominated by a
handful of steps and the percentile is not.
"""
import argparse
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = HERE.parents[1]
BINARY = ARTIFACT_ROOT / "bin" / "kappa-fees"

PARAM_MIN, PARAM_MAX, PARAM_STEP = 0.0, 16.0, 0.5
ALPHA_MIN, ALPHA_MAX = 0.01, 0.99
EQUILIBRIUM_PRICE = 1.0
START_STEP = 100

DISTRIBUTIONS = {
    "Spike": [0, 0, 0, 0, 1],
    "Uniform": [0.2, 0.2, 0.2, 0.2, 0.2],
    "Bimodal": [0.4, 0, 0.2, 0, 0.4],
}


def alpha_from_parameter(parameter):
    return ALPHA_MIN + (parameter - PARAM_MIN) / (PARAM_MAX - PARAM_MIN) * (ALPHA_MAX - ALPHA_MIN)


def fee_series(mode, distribution, parameter, alpha, total_steps, mempool):
    """The three chains' base-fee trajectories for one sweep point."""
    result = subprocess.run(
        [str(BINARY), "-mode", mode, "-dist", distribution,
         "-param", f"{parameter}", "-alpha", f"{alpha}",
         "-total-steps", str(total_steps), "-mempool", str(mempool)],
        capture_output=True, check=True)
    values = np.frombuffer(result.stdout, dtype="<f8")
    return values.reshape(3, -1)


def kappa_defense_series(delta_p, weights, start_idx, end_idx):
    """Chain 0's same-sign delayed self-reinforcement, Eq. B.1."""
    dmax = len(weights)
    end_idx = min(end_idx, len(delta_p) - 1)
    if start_idx + dmax > end_idx:
        return []
    ks = []
    eps = 1e-12
    for t in range(start_idx + dmax, end_idx + 1):
        cur = delta_p[t]
        if not np.isfinite(cur) or abs(cur) < eps:
            continue
        s_cur = np.sign(cur)
        k = 0.0
        for d in range(1, dmax + 1):
            prev = delta_p[t - d]
            if not np.isfinite(prev) or prev == 0.0:
                continue
            if np.sign(prev) == s_cur:
                k += weights[d - 1] * (abs(prev) / abs(cur))
        ks.append(k)
    return ks


def kappa_attack_series(delta_p_i, delta_p_j, weights, start_idx, end_idx):
    """A peer's opposite-sign delayed force on Chain 0, Eq. B.2."""
    dmax = len(weights)
    end_idx = min(end_idx, len(delta_p_i) - 1, len(delta_p_j) - 1)
    if start_idx + dmax > end_idx:
        return []
    ks = []
    eps = 1e-12
    for t in range(start_idx + dmax, end_idx + 1):
        cur_j = delta_p_j[t]
        cur_i = delta_p_i[t]
        if not np.isfinite(cur_j) or abs(cur_j) < eps:
            continue
        s_i = np.sign(cur_i)
        k = 0.0
        for d in range(1, dmax + 1):
            prev_j = delta_p_j[t - d]
            if not np.isfinite(prev_j) or prev_j == 0.0:
                continue
            if np.sign(prev_j) != s_i:
                k += weights[d - 1] * (abs(prev_j) / abs(cur_j))
        ks.append(k)
    return ks


def sweep(mode, output_dir, total_steps, mempool):
    parameters = np.arange(PARAM_MIN, PARAM_MAX + 1e-9, PARAM_STEP)
    frames = []
    for distribution, weights in DISTRIBUTIONS.items():
        rows = []
        for parameter in parameters:
            alpha = alpha_from_parameter(parameter)
            fees = fee_series(mode, distribution, parameter, alpha, total_steps, mempool)
            deviations = fees - EQUILIBRIUM_PRICE
            end_idx = fees.shape[1] - 1
            if mode == "defense":
                series = kappa_defense_series(deviations[0], weights, START_STEP, end_idx)
                percentile = float(np.percentile(series, 90)) if series else np.nan
                maximum = float(np.max(series)) if series else np.nan
            else:
                first = kappa_attack_series(deviations[0], deviations[1], weights,
                                            START_STEP, end_idx)
                second = kappa_attack_series(deviations[0], deviations[2], weights,
                                             START_STEP, end_idx)
                if first and second:
                    percentile = 0.5 * (float(np.percentile(first, 90))
                                        + float(np.percentile(second, 90)))
                    maximum = float(max(np.max(first), np.max(second)))
                else:
                    percentile = maximum = np.nan
            rows.append({
                "distribution": distribution,
                ("epsilon_j0" if mode == "defense" else "lambda_j0"): float(parameter),
                "alpha_j0_in": float(alpha),
                "p90_kappa": percentile,
                "max_kappa": maximum,
            })
            print(f"[{mode}][{distribution}] param={parameter:4.1f} alpha={alpha:.3f} "
                  f"p90={percentile:.4f} max={maximum:.4g}", flush=True)
        frame = pd.DataFrame(rows)
        frame.to_csv(output_dir / f"kappa_scan_{distribution}.csv", index=False)
        frames.append(frame)
    combined = pd.concat(frames, ignore_index=True)
    for distribution in DISTRIBUTIONS:
        part = combined[combined["distribution"] == distribution]
        print(f"[{mode}] {distribution}: p90 peaks at {part['p90_kappa'].max():.2f}, "
              f"max peaks at {part['max_kappa'].max():.4g}")
    return combined


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["defense", "attack"], required=True)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--total-steps", type=int, default=50100)
    parser.add_argument("--mempool", type=float, default=20.0)
    args = parser.parse_args()
    output_dir = args.output_dir or (HERE / ("defense-channel" if args.mode == "defense"
                                             else "attack-channel"))
    output_dir.mkdir(parents=True, exist_ok=True)
    if not BINARY.exists():
        raise SystemExit(f"{BINARY} not found, run ./build.sh first")
    sweep(args.mode, output_dir, args.total_steps, args.mempool)


if __name__ == "__main__":
    main()
