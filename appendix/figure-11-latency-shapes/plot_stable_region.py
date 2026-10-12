"""Figure 11a-b -- the Figure 4a stable region under bimodal and uniform latency.

Both panels are drawn by `figure-style/boundary_panel.py`, so they carry the
Figure 4a contract: converged cells left white, unstable cells sized by the
realized load standard deviation and coloured by the share of blocks that reach
the gas limit, and one canvas size for every panel.
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
DATA_TEMPLATE = "convergence_results_{}.csv"
X_COLUMN = "epsilon_j0"


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
                   f"over-correction-bubble-chart-{distribution_name.lower()}.pdf")
    result = boundary_panel.render_panel(
        frame,
        output_path,
        x_column=X_COLUMN,
        x_label=r"$\epsilon_{j0}$",
        x_axis=boundary_panel.EPSILON_AXIS,
        y_column="alpha_inflow",
        y_label=r"$\sum \alpha_{j\to 0,\mathrm{in}}$",
    )
    boundary_panel.report(result)
    return output_path


def analyze_bubble_metrics(frame, distribution_name):
    print(f"\n{distribution_name} distribution")
    print(f"  M_ext rho range: {frame['mext_rho'].min():.6f} - {frame['mext_rho'].max():.6f}")
    print(f"  Load std range: {frame['load_std'].min():.6f} - {frame['load_std'].max():.6f}")
    unstable = frame.loc[~frame["converged"]]
    if unstable.empty:
        return
    print(f"  Full-block share range over unstable cells: 0 - {unstable['full_pct'].max():.2f}%")
    print(f"  Unstable cells that never fill a block: {(unstable['full_pct'] == 0).sum()}")
    column = frame.loc[frame["alpha_inflow"].round(2).eq(0.97)]
    stable = column.loc[column["converged"], X_COLUMN]
    if len(stable):
        print(f"  Max stable epsilon_j0 at alpha=0.97: {stable.max():.1f}")


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
