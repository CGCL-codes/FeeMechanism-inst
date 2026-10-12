import argparse
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import Normalize

HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = next(parent for parent in HERE.parents if (parent / "figure-style").is_dir())
sys.path.insert(0, str(ARTIFACT_ROOT / "figure-style"))

# The same ramp the boundary maps use, so a colour means the same share of full
# blocks here as it does on Figure 4.
from boundary_panel import COLORMAP  # noqa: E402

GRID_STEP = 0.001
COUNT = 125
DELTAS = np.arange(1, COUNT + 1) * GRID_STEP
WEIGHTS = np.array([0.0, 0.0, 0.0, 0.0, 1.0])
BASE_ELASTICITY = 1.5
INBOUND_ELASTICITY = 16.0

EPSILON = np.full((3, 3), INBOUND_ELASTICITY)
np.fill_diagonal(EPSILON, 0.0)

SHARES_LOCAL20 = np.array([
    [0.20, 0.00, 0.00],
    [0.40, 0.10, 0.25],
    [0.40, 0.25, 0.10],
])
SHARES_OUTBOUND20 = np.array([
    [0.00, 0.10, 0.10],
    [0.40, 0.00, 0.25],
    [0.40, 0.25, 0.00],
])
LAMBDA_BASE = np.full((3, 3), BASE_ELASTICITY)
LAMBDA_INBOUND16 = np.array([
    [BASE_ELASTICITY, BASE_ELASTICITY, BASE_ELASTICITY],
    [INBOUND_ELASTICITY, BASE_ELASTICITY, BASE_ELASTICITY],
    [INBOUND_ELASTICITY, BASE_ELASTICITY, BASE_ELASTICITY],
])

CONFIGURATIONS = {
    "baseline": {
        "csv": "baseline_local20.csv",
        "shares": SHARES_LOCAL20,
        "lambda": LAMBDA_BASE,
        "panels": ("a", "b"),
    },
    "outbound20": {
        "csv": "outbound20.csv",
        "shares": SHARES_OUTBOUND20,
        "lambda": LAMBDA_BASE,
        "panels": ("c", "d"),
    },
    "lambda16": {
        "csv": "lambda16.csv",
        "shares": SHARES_LOCAL20,
        "lambda": LAMBDA_INBOUND16,
        "panels": ("e", "f"),
    },
}


def companion(deltas, shares, lam, eps, weights):
    deltas = np.asarray(deltas, dtype=float)
    shares = np.asarray(shares, dtype=float)
    lam = np.asarray(lam, dtype=float)
    eps = np.asarray(eps, dtype=float)
    weights = np.asarray(weights, dtype=float)
    n = shares.shape[0]
    dmax = len(weights)

    inst_self = (lam * shares).sum(axis=1)
    a0 = -deltas[:, None] * eps * shares
    np.fill_diagonal(a0, 1.0 - deltas * inst_self)

    delayed = np.zeros((n, n))
    for i in range(n):
        delayed[i, i] = sum(eps[j, i] * shares[j, i] for j in range(n) if j != i)
        for j in range(n):
            if j != i:
                delayed[i, j] = lam[j, i] * shares[j, i]

    size = n * (dmax + 1)
    matrix = np.zeros((size, size))
    matrix[:n, :n] = a0
    for k, weight in enumerate(weights, start=1):
        matrix[:n, k * n:(k + 1) * n] = -weight * deltas[:, None] * delayed
    matrix[n:, :-n] = np.eye(n * dmax)
    return matrix


def stability_grid(shares, lam):
    grid = np.zeros((COUNT, COUNT))
    for i, delta_zero in enumerate(DELTAS):
        for j, delta_peer in enumerate(DELTAS):
            matrix = companion([delta_zero, delta_peer, delta_peer], shares, lam, EPSILON, WEIGHTS)
            grid[i, j] = np.abs(np.linalg.eigvals(matrix)).max()
    return grid < 1.0


def prefix_max(column):
    run = 0
    for value in column:
        if not value:
            break
        run += 1
    return DELTAS[run - 1] if run else np.nan


def report(name, frame, stable):
    agree = (frame["sim"] == frame["rho_stable"]).sum()
    delta_zero_max = np.array([prefix_max(stable[:, j]) for j in range(COUNT)])
    delta_peer_max = np.array([prefix_max(stable[i, :]) for i in range(COUNT)])
    peer_bound = delta_peer_max[0]
    inside = delta_zero_max[:int(np.searchsorted(DELTAS, peer_bound))]
    print(f"[{name}] simulation/M_ext agreement {agree}/{len(frame)} ({agree / len(frame) * 100:.2f}%)")
    print(f"[{name}] delta_peer_max = {peer_bound:.3f}")
    print(f"[{name}] delta_0_max = {delta_zero_max[0]:.3f}, widening to {np.nanmax(inside):.3f}")
    print(f"[{name}] max chain-0 full blocks {frame['full_block0'].max() * 100:.1f}%, "
          f"max peer full blocks "
          f"{np.maximum(frame['full_block1'], frame['full_block2']).max() * 100:.1f}%")
    print(f"[{name}] max chain-0 inflation {frame['inflation0'].max() * 100:.1f}%, "
          f"max peer inflation {np.maximum(frame['inflation1'], frame['inflation2']).max() * 100:.1f}%")


def colour_scale(maximum):
    """One scale for all six panels, spanning the share they actually reach.

    The six panels are read against each other -- Chain 0 against its peers
    under the same configuration -- so they share a scale rather than each
    taking its own. Ticks are the round decades below the maximum, which is
    always the last tick, the same rule the boundary maps use.
    """
    vmax = max(1.0, float(np.ceil(maximum * 100.0)))
    ticks = [value for value in (0, 10, 20, 30, 40, 50, 60, 70, 80, 90) if value <= 0.88 * vmax]
    labels = [f"{value:g}%" for value in ticks] + [f"{vmax:.0f}%"]
    return vmax, ticks + [vmax], labels


def draw(values, stable, output_path, scale):
    vmax, ticks, labels = scale
    norm = Normalize(vmin=0.0, vmax=vmax)
    figure, axis = plt.subplots(figsize=(4.5, 3.9))
    image = axis.imshow(values.T, origin="lower", aspect="auto", cmap=COLORMAP, norm=norm,
                        extent=(DELTAS[0], DELTAS[-1], DELTAS[0], DELTAS[-1]),
                        interpolation="nearest")
    axis.contour(DELTAS, DELTAS, stable.T.astype(float), levels=[0.5],
                 colors="0.15", linewidths=2.6)
    axis.set_xlabel(r"$\delta_0$")
    axis.set_ylabel(r"$\delta_{\mathrm{peer}}$")
    colorbar = figure.colorbar(image, ax=axis, fraction=0.046, pad=0.03, ticks=ticks)
    colorbar.ax.set_yticklabels(labels)
    colorbar.set_label("% full blocks", rotation=270, labelpad=14)
    figure.tight_layout()
    figure.savefig(output_path)
    plt.close(figure)
    print(f"[OK] {output_path}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    parser.add_argument("--configuration", choices=sorted(CONFIGURATIONS) + ["all"], default="all")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    selected = sorted(CONFIGURATIONS) if args.configuration == "all" else [args.configuration]
    frames = {name: pd.read_csv(args.input_dir / CONFIGURATIONS[name]["csv"])
              for name in selected}
    scale = colour_scale(max(
        max(float(frame["full_block0"].max()),
            float(np.maximum(frame["full_block1"], frame["full_block2"]).max()))
        for frame in frames.values()))
    print(f"[scale] colour bar spans 0 to {scale[0]:g}% full blocks")

    for name in selected:
        spec = CONFIGURATIONS[name]
        stable = stability_grid(spec["shares"], spec["lambda"])
        frame = frames[name]
        frame["i"] = np.rint(frame["delta0"] / GRID_STEP).astype(int) - 1
        frame["j"] = np.rint(frame["delta1"] / GRID_STEP).astype(int) - 1
        frame["sim"] = frame["converged_all"].astype(str).str.strip().str.lower().eq("true")
        frame["rho_stable"] = stable[frame["i"], frame["j"]]
        report(name, frame, stable)

        chain_zero = np.zeros((COUNT, COUNT))
        peers = np.zeros((COUNT, COUNT))
        chain_zero[frame["i"], frame["j"]] = 100 * frame["full_block0"].clip(lower=0)
        peers[frame["i"], frame["j"]] = 100 * np.maximum(
            frame["full_block1"], frame["full_block2"]).clip(lower=0)

        panel_zero, panel_peer = spec["panels"]
        draw(chain_zero, stable, args.output_dir / f"figure-06{panel_zero}.pdf", scale)
        draw(peers, stable, args.output_dir / f"figure-06{panel_peer}.pdf", scale)


if __name__ == "__main__":
    main()
