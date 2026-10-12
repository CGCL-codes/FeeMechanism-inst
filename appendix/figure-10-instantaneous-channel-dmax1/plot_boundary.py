"""Boundary maps of the appendix, drawn in the Figure 4a style.

One script serves Figures 9, 10, 12 and 13. Every panel is drawn by
`figure-style/boundary_panel.py`, which holds the Figure 4a contract: converged
cells left white, unstable cells as bubbles sized by the realized load standard
deviation and coloured by the share of blocks that reach the gas limit, the
simulated and M_ext boundaries on top, and one canvas size for every panel.

The colour bar spans each panel's own range, so a panel that saturates 6% of
its blocks spends the whole ramp on that 6%.
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = next(parent for parent in HERE.parents if (parent / "figure-style").is_dir())
sys.path.insert(0, str(ARTIFACT_ROOT / "figure-style"))

import boundary_panel  # noqa: E402


FIGURE_SPECS = {
    "fig9-top": {
        "x_column": "lambda_j0",
        "alpha_column": "alpha_inflow",
        "x_label": r"$\lambda_{j0}$",
        "y_label": r"$\sum \alpha_{j\to 0,\mathrm{in}}$",
        "x_axis": boundary_panel.EPSILON_AXIS,
        "panels": [
            ("attack_defense_results_Bimodal.csv", "converged-attack-defense-bubble-chart-bimodal.pdf"),
            ("attack_defense_results_Uniform.csv", "converged-attack-defense-bubble-chart-uniform.pdf"),
            ("attack_defense_results_Spike.csv", "converged-attack-defense-bubble-chart-spike.pdf"),
        ],
    },
    "fig9-bottom": {
        "x_column": "epsilon_0j",
        "alpha_column": "alpha_outflow",
        "x_label": r"$\epsilon_{0j}$",
        "y_label": r"$\sum \alpha_{0\to j,\mathrm{out}}$",
        "x_axis": boundary_panel.EPSILON_AXIS,
        "panels": [
            ("attack_defense_results_Bimodal.csv", "attack-defense-bubble-chart-bimodal.pdf"),
            ("attack_defense_results_Uniform.csv", "attack-defense-bubble-chart-uniform.pdf"),
            ("attack_defense_results_Spike.csv", "attack-defense-bubble-chart-spike.pdf"),
        ],
    },
    "fig10": {
        "x_column": "epsilon_0j",
        "alpha_column": "alpha_outflow",
        "x_label": r"$\epsilon_{0j}$",
        "y_label": r"$\sum \alpha_{0\to j,\mathrm{out}}$",
        "x_axis": boundary_panel.EPSILON_AXIS,
        "panels": [
            ("attack_defense_results_Spike.csv", "boundary-attack-without-latency.pdf"),
        ],
    },
    "fig12": {
        "x_column": "epsilon_j0",
        "alpha_column": "alpha_inflow",
        "x_label": r"$\epsilon_{j0}$",
        "y_label": r"$\sum \alpha_{j\to 0,\mathrm{in}}$",
        "x_axis": boundary_panel.EPSILON_AXIS,
        "panels": [
            ("dmax5/convergence_results_Uniform.csv", "latency5-over-correction-bubble-chart-uniform.pdf"),
            ("dmax5/convergence_results_Spike.csv", "latency5-over-correction-bubble-chart-spike.pdf"),
            ("dmax7/convergence_results_Uniform.csv", "latency7-over-correction-bubble-chart-uniform.pdf"),
            ("dmax7/convergence_results_Spike.csv", "latency7-over-correction-bubble-chart-spike.pdf"),
            ("dmax10/convergence_results_Uniform.csv", "latency10-over-correction-bubble-chart-uniform.pdf"),
            ("dmax10/convergence_results_Spike.csv", "latency10-over-correction-bubble-chart-spike.pdf"),
        ],
    },
    "fig13": {
        "x_column": "epsilon_j0",
        "alpha_column": "alpha_inflow",
        "x_label": r"$\epsilon_{j0}$",
        "y_label": r"$\sum \alpha_{j\to 0,\mathrm{in}}$",
        "x_axis": boundary_panel.EPSILON_AXIS,
        "panels": [
            ("convergence_results_spike_shard5.csv", "over-correction-bubble-chart-5.pdf"),
            ("convergence_results_spike_shard7.csv", "over-correction-bubble-chart-7.pdf"),
            ("convergence_results_spike_shard10.csv", "over-correction-bubble-chart-10.pdf"),
        ],
    },
}


def validate_frame(frame, x_column, alpha_column, source="data"):
    frame = boundary_panel.prepare(frame, source, x_column=x_column, y_column=alpha_column)
    if "classification_match" not in frame.columns:
        raise ValueError(f"{source} is missing required columns: classification_match")
    frame["classification_match"] = boundary_panel.boolean_series(frame["classification_match"])
    for column in (x_column, alpha_column, "load_std", "load_inflation",
                   "full_block_fraction", "mext_rho"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if not np.isfinite(frame[column].to_numpy()).all():
            raise ValueError(f"{source} contains non-finite {column} values")
    rho_stable = frame["mext_rho"].lt(1.0)
    if not frame["mext_stable"].equals(rho_stable):
        raise ValueError(f"{source} has mext_stable values inconsistent with mext_rho < 1")
    if not frame["classification_match"].equals(frame["converged"].eq(frame["mext_stable"])):
        raise ValueError(f"{source} has inconsistent classification_match values")
    return frame


def panel_summary(frame, x_column, alpha_column):
    unstable = frame.loc[~frame["converged"]]
    summary = {
        "rows": int(len(frame)),
        "converged": int(frame["converged"].sum()),
        "unstable": int((~frame["converged"]).sum()),
        "max_full_block_pct": float(unstable["full_pct"].max()) if len(unstable) else 0.0,
        "max_inflation_pct": float(unstable["inflation_pct"].max()) if len(unstable) else 0.0,
        "max_load_std": float(frame["load_std"].max()),
        "transition_columns": len(
            boundary_panel.transition_points(frame, x_column, alpha_column, "converged")),
        "mext_stable": int(frame["mext_stable"].sum()),
        "mext_unstable": int((~frame["mext_stable"]).sum()),
        "mext_transition_columns": len(
            boundary_panel.transition_points(frame, x_column, alpha_column, "mext_stable")),
        "classification_matches": int(frame["classification_match"].sum()),
        "classification_agreement": float(frame["classification_match"].mean()),
        "simulation_stable_mext_unstable": int((frame["converged"] & ~frame["mext_stable"]).sum()),
        "simulation_unstable_mext_stable": int((~frame["converged"] & frame["mext_stable"]).sum()),
    }
    if len(unstable):
        minimum_x = float(unstable[x_column].min())
        at_minimum_x = unstable.loc[np.isclose(unstable[x_column], minimum_x)]
        summary.update({
            "minimum_unstable_parameter": minimum_x,
            "minimum_unstable_alpha": float(at_minimum_x[alpha_column].min()),
            "maximum_unstable_alpha_at_minimum_parameter": float(at_minimum_x[alpha_column].max()),
            "boundary_reduction_from_16": (16.0 - minimum_x) / 16.0,
            "never_full_cells": int((unstable["full_pct"] == 0).sum()),
        })
    mext_unstable = frame.loc[~frame["mext_stable"]]
    if len(mext_unstable):
        minimum_x = float(mext_unstable[x_column].min())
        at_minimum_x = mext_unstable.loc[np.isclose(mext_unstable[x_column], minimum_x)]
        summary.update({
            "mext_minimum_unstable_parameter": minimum_x,
            "mext_minimum_unstable_alpha": float(at_minimum_x[alpha_column].min()),
            "mext_maximum_unstable_alpha_at_minimum_parameter": float(at_minimum_x[alpha_column].max()),
        })
    return summary


def render_figure(figure, input_dir, output_dir):
    spec = FIGURE_SPECS[figure]
    input_dir = Path(input_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    summaries = {}
    for input_name, output_name in spec["panels"]:
        input_path = input_dir / input_name
        if not input_path.exists():
            raise FileNotFoundError(input_path)
        frame = validate_frame(pd.read_csv(input_path), spec["x_column"],
                               spec["alpha_column"], source=str(input_path))
        result = boundary_panel.render_panel(
            frame,
            output_dir / output_name,
            x_column=spec["x_column"],
            x_label=spec["x_label"],
            x_axis=spec["x_axis"],
            y_column=spec["alpha_column"],
            y_label=spec["y_label"],
        )
        boundary_panel.report(result)
        summaries[output_name] = panel_summary(frame, spec["x_column"], spec["alpha_column"])
    return summaries


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--figure", required=True, choices=list(FIGURE_SPECS),
                        help="the paper figure to render")
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--summary-json", type=Path)
    args = parser.parse_args(argv)

    summaries = render_figure(args.figure, args.input_dir, args.output_dir)
    encoded = json.dumps(summaries, indent=2, sort_keys=True)
    print(encoded)
    if args.summary_json:
        args.summary_json.parent.mkdir(parents=True, exist_ok=True)
        args.summary_json.write_text(encoded + "\n")


if __name__ == "__main__":
    main()
