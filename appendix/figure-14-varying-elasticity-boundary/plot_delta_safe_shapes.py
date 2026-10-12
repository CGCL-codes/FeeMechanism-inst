"""Figure 14 -- Delta_safe under the three price-dependent elasticity shapes.

The Figure 4c grid rerun with `epsilon_{j->0}` a function of Chain 0's own base
fee. Each panel is drawn by `figure-style/boundary_panel.py`, so all three carry
the Figure 4a contract, with the colour bar spanning each panel's own range of
the full-block share.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = next(parent for parent in HERE.parents if (parent / "figure-style").is_dir())
sys.path.insert(0, str(ARTIFACT_ROOT / "figure-style"))

import boundary_panel  # noqa: E402

SHAPES = ["log", "linear", "logistic"]
MONOLITHIC_BOUNDARY = 0.125
X_COLUMN = "delta"


def analyze_bubble_metrics(frame, label):
    print(f"\n{label}")
    print(f"  M_ext rho range: {frame['mext_rho'].min():.6f} - {frame['mext_rho'].max():.6f}")
    print(f"  Load std range: {frame['load_std'].min():.6f} - {frame['load_std'].max():.6f}")
    if {"eps_min", "eps_max"}.issubset(frame.columns):
        print(f"  Elasticity range along the trajectories: "
              f"{frame['eps_min'].min():.3f} - {frame['eps_max'].max():.3f}")
    diverged = frame.loc[~frame["converged"]].dropna(subset=[X_COLUMN])
    if diverged.empty:
        return
    print(f"  Full-block share range over unstable cells: 0 - {diverged['full_pct'].max():.2f}%")
    print(f"  Unstable cells that never fill a block: {(diverged['full_pct'] == 0).sum()}")
    delta_safe = float(diverged[X_COLUMN].min())
    shrinkage = max(0.0, (1.0 - delta_safe / MONOLITHIC_BOUNDARY) * 100.0)
    print(f"  Delta_safe: [0, {delta_safe:.3f}); shrinkage: {shrinkage:.1f}%")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    parser.add_argument("--shapes", nargs="+", choices=SHAPES, default=SHAPES)
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    for shape in args.shapes:
        path = args.input_dir / f"convergence_results_delta_{shape}_Spike.csv"
        if not path.exists():
            raise SystemExit(f"missing {path}")
        frame = boundary_panel.prepare(pd.read_csv(path), path,
                                       x_column=X_COLUMN, y_column="alpha_inflow")
        print(f"[OK] Loaded {path}: {len(frame)} records")
        analyze_bubble_metrics(frame, f"Spike ({shape})")
        result = boundary_panel.render_panel(
            frame,
            args.output_dir / f"varying-elasticity-boundary-{shape}.pdf",
            x_column=X_COLUMN,
            x_label=r"$\delta$",
            x_axis=boundary_panel.DELTA_AXIS,
            y_column="alpha_inflow",
            y_label=r"$\sum \alpha_{j\to 0,\mathrm{in}}$",
        )
        boundary_panel.report(result)


if __name__ == "__main__":
    main()
