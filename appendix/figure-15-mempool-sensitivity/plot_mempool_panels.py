"""Figure 15 -- the Figure 4a stable region at four transaction-pool bounds.

The Figure 4a scan rerun at Q = 10, 20, 50 and 100 block gas limits, with the
grid, the shock, the latency shape and the convergence test of Section 7.2 left
untouched. Each panel is drawn by `figure-style/boundary_panel.py`, so all four
carry the Figure 4a contract. Each panel's colour bar is topped at the largest
share of full blocks that the panel itself reaches, because that share is the
only quantity the pool bound moves.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = next(parent for parent in HERE.parents if (parent / "figure-style").is_dir())
sys.path.insert(0, str(ARTIFACT_ROOT / "figure-style"))

import boundary_panel  # noqa: E402

CAPACITIES = [10, 20, 50, 100]
BASELINE = 20


def analyze(frame, capacity):
    unstable = frame.loc[~frame["converged"]]
    agreement = (frame["converged"] == frame["mext_stable"]).sum()
    print(f"\nQ = {capacity}")
    print(f"  unstable cells: {len(unstable)} of {len(frame)}")
    print(f"  full-block share up to {unstable['full_pct'].max():.2f}%")
    print(f"  unstable cells that never fill a block: {(unstable['full_pct'] == 0).sum()}")
    print(f"  load inflation up to {unstable['inflation_pct'].max():.4f}%")
    print(f"  simulation/M_ext agreement: {agreement}/{len(frame)}")
    return unstable


def compare(frames):
    """The two claims of the appendix: the verdict never moves, the colour barely does."""
    key = ["epsilon_j0", "alpha_inflow"]
    base = frames[BASELINE].set_index(key)
    print(f"\nVerdict against Q = {BASELINE}")
    for capacity in CAPACITIES:
        other = frames[capacity].set_index(key)
        print(f"  Q = {capacity:>3}: {(other['converged'] != base['converged']).sum()} cells change verdict")

    low = frames[CAPACITIES[0]].set_index(key)
    high = frames[CAPACITIES[-1]].set_index(key)
    unstable = low.index[~low["converged"]]
    drift = high.loc[unstable, "full_pct"].to_numpy() - low.loc[unstable, "full_pct"].to_numpy()
    identical = int(np.isclose(drift, 0.0, atol=1e-12).sum())
    print(f"\nQ = {CAPACITIES[0]} against Q = {CAPACITIES[-1]}, over {len(unstable)} unstable cells")
    print(f"  report exactly the same share: {identical} ({100 * identical / len(unstable):.1f}%)")
    print(f"  largest change: {np.abs(drift).max():.2f} percentage points")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    frames = {}
    for capacity in CAPACITIES:
        path = args.input_dir / f"convergence_results_Spike_q{capacity}.csv"
        if not path.exists():
            raise SystemExit(f"missing {path}")
        frame = boundary_panel.prepare(pd.read_csv(path), path,
                                       x_column="epsilon_j0", y_column="alpha_inflow")
        frames[capacity] = frame
        analyze(frame, capacity)
        boundary_panel.report(boundary_panel.render_panel(
            frame,
            args.output_dir / f"over-correction-bubble-chart-spike-q{capacity}.pdf",
            x_column="epsilon_j0", x_label=r"$\epsilon_{j0}$",
            x_axis=boundary_panel.EPSILON_AXIS,
            y_column="alpha_inflow", y_label=r"$\sum \alpha_{j\to 0,\mathrm{in}}$",
        ))

    compare(frames)


if __name__ == "__main__":
    main()
