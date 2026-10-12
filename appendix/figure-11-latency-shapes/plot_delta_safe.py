"""Figure 11c-d -- Delta_safe under bimodal and uniform latency.

The Figure 4c grid drawn in the Figure 4a style, panel for panel. Rendering is
delegated to `figure-style/boundary_panel.py`, which holds that contract.
"""
import argparse
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = next(parent for parent in HERE.parents if (parent / "figure-style").is_dir())
sys.path.insert(0, str(ARTIFACT_ROOT / "figure-style"))

import boundary_panel  # noqa: E402

DISTRIBUTIONS = ["Spike", "Uniform", "Bimodal"]
DATA_TEMPLATE = "convergence_results_delta_{}.csv"
MONOLITHIC_BOUNDARY = 0.125
X_COLUMN = "delta"


def load_convergence_data(input_dir=Path("data"), distributions=None):
    input_dir = Path(input_dir)
    data = {}
    for distribution in (distributions or DISTRIBUTIONS):
        path = input_dir / DATA_TEMPLATE.format(distribution)
        if not path.exists():
            print(f"[ERROR] File not found: {path}")
            return None
        frame = boundary_panel.prepare(pd.read_csv(path), path,
                                       x_column=X_COLUMN, y_column="alpha_inflow")
        print(f"[OK] Loaded {path}: {len(frame)} records")
        data[distribution] = frame
    return data


def create_single_bubble_chart(frame, distribution_name, output_dir=Path(".")):
    output_path = (Path(output_dir) /
                   f"over-correction-bubble-chart-delta-{distribution_name.lower()}.pdf")
    result = boundary_panel.render_panel(
        frame,
        output_path,
        x_column=X_COLUMN,
        x_label=r"$\delta$",
        x_axis=boundary_panel.DELTA_AXIS,
        y_column="alpha_inflow",
        y_label=r"$\sum \alpha_{j\to 0,\mathrm{in}}$",
    )
    boundary_panel.report(result)
    return output_path


def analyze_bubble_metrics(frame, distribution_name):
    print(f"\n{distribution_name} distribution")
    print(f"  M_ext rho range: {frame['mext_rho'].min():.6f} - {frame['mext_rho'].max():.6f}")
    print(f"  Load std range: {frame['load_std'].min():.6f} - {frame['load_std'].max():.6f}")
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
    parser.add_argument("--distributions", nargs="+", choices=DISTRIBUTIONS)
    args = parser.parse_args(argv)

    selected = args.distributions or [
        distribution for distribution in DISTRIBUTIONS
        if (args.input_dir / DATA_TEMPLATE.format(distribution)).exists()
    ]
    if not selected:
        raise SystemExit(f"no result CSV found under {args.input_dir}")

    data = load_convergence_data(args.input_dir, selected)
    if data is None:
        raise SystemExit(1)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for distribution in selected:
        frame = data[distribution]
        analyze_bubble_metrics(frame, distribution)
        create_single_bubble_chart(frame, distribution, args.output_dir)


if __name__ == "__main__":
    main()
