"""Figure 4 — Pathway 1 under spike latency, three panels.

Each panel is written as its own PDF at the same canvas size, so LaTeX scales
them to the same height when it places them side by side.

  (a) stable region at delta = 0.125, coloured by the share of full blocks
  (b) that share against rho(M_ext), the strength of the instability
  (c) Delta_safe at elasticity 16, coloured by the same share

Panels (a) and (c) share one colour scale that tops out at the share of full
blocks in the configuration that attains the load-inflation bound of Section 3,
so a colour means the same thing in either panel.
"""

import argparse
import math
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from mpl_toolkits.axes_grid1 import make_axes_locatable

HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = next(parent for parent in HERE.parents if (parent / "figure-style").is_dir())
sys.path.insert(0, str(ARTIFACT_ROOT / "figure-style"))

# The whole panel style lives in figure-style/boundary_panel.py, which every
# appendix boundary map also reads. Importing the constants rather than copying
# them is what keeps Figure 4 and the appendix panels identical: one colour
# ramp, one set of font sizes, one colour-bar geometry, one tick rule.
from boundary_panel import (  # noqa: E402
    AXIS_LABEL_FONT_SIZE,
    BUBBLE_SCALE,
    COLORBAR_LABEL,
    COLORBAR_LABEL_FONT_SIZE,
    COLORBAR_LABEL_PAD,
    COLORBAR_PAD,
    COLORBAR_SIZE,
    COLORBAR_TICK_FONT_SIZE,
    COLORMAP,
    FIGSIZE,
    LAYOUT_RECT,
    LEGEND_FONT_SIZE,
    MINIMUM_BUBBLE_SIZE,
    RASTER_DPI,
    TICK_FONT_SIZE,
    Y_TICKS,
    BOUNDARY_LINEWIDTH,
    MEXT_LINEWIDTH,
    MEXT_DASHES,
    colorbar_ticks,
    draw_boundary,
)

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "pdf.compression": 9,
    }
)

SIMULATED_COLOR = "darkred"
MEXT_COLOR = "#1764ab"
CEILING_COLOR = "#c0392b"
# Panel (b) carries a single reference line rather than a pair of boundaries,
# so it does not need the weight that keeps two overlapping curves apart.
CEILING_LINEWIDTH = 3.0
UNSATURATED_LINEWIDTH = 2.2
FULL_COLOR = "#31688e"

DELTA = 0.125
# Share of full blocks in the configuration that attains the inflation bound.
FULL_CEILING = 100.0 / (1 - math.log(1 + DELTA) / math.log(1 - DELTA))
INFLATION_CEILING = 2 * FULL_CEILING - 100.0

REQUIRED_COLUMNS = {"alpha_inflow", "load_std", "load_inflation", "converged",
                    "full_block_fraction", "mext_rho", "mext_stable"}


def boolean_series(series):
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    unknown = ~normalized.isin({"true", "false", "1", "0"})
    if unknown.any():
        raise ValueError(f"Unrecognized Boolean values: {sorted(normalized[unknown].unique())}")
    return normalized.isin({"true", "1"})


def load(path, x_column):
    frame = pd.read_csv(path)
    missing = sorted((REQUIRED_COLUMNS | {x_column}).difference(frame.columns))
    if missing:
        raise SystemExit(f"{path} is missing columns: {', '.join(missing)}. "
                         "Run mext-criterion/mext_criterion.py on it first.")
    frame["converged"] = boolean_series(frame["converged"])
    frame["mext_stable"] = boolean_series(frame["mext_stable"])
    frame["full_pct"] = 100 * frame["full_block_fraction"]
    frame["inflation_pct"] = 100 * frame["load_inflation"]
    return frame


def transition_points(frame, x_column, state_column):
    points = []
    for x_value, group in frame.groupby(x_column, sort=True):
        group = group.sort_values("alpha_inflow")
        alphas = group["alpha_inflow"].to_numpy(dtype=float)
        stable = group[state_column].to_numpy(dtype=bool)
        transitions = [
            (alphas[index] + alphas[index + 1]) / 2.0
            for index in range(len(group) - 1)
            if stable[index] and not stable[index + 1]
        ]
        if transitions:
            points.append((float(x_value), float(transitions[0])))
    return points


def plot_transition_boundary(axes, points, *, color, linestyle):
    """Delegates to the shared renderer, so Figure 4's boundaries carry exactly
    the weight and halo that every appendix panel carries."""
    solid = linestyle == "-"
    if not draw_boundary(axes, points, color=color,
                         linestyle="-" if solid else MEXT_DASHES,
                         linewidth=BOUNDARY_LINEWIDTH if solid else MEXT_LINEWIDTH,
                         zorder=4 if solid else 5):
        print(f"[WARN] fewer than two boundary points for {color}")


def render_map(frame, x_column, x_label, x_limit, x_ticks, output):
    figure, axes = plt.subplots(figsize=FIGSIZE)
    axes.set_rasterization_zorder(2)

    # Converged cells are left white, so the stable region reads as empty.
    unstable = frame.loc[~frame["converged"]]
    bubble_sizes = np.maximum(
        unstable["load_std"].to_numpy(dtype=float) * BUBBLE_SCALE, MINIMUM_BUBBLE_SIZE)
    observed_max = float(unstable["full_pct"].max())
    scatter = axes.scatter(
        unstable[x_column], unstable["alpha_inflow"],
        s=bubble_sizes, c=unstable["full_pct"],
        vmin=0.0, vmax=observed_max, alpha=0.6, cmap=COLORMAP,
        edgecolors="none", linewidths=0, rasterized=True, zorder=1,
    )

    plot_transition_boundary(axes, transition_points(frame, x_column, "converged"),
                             color=SIMULATED_COLOR, linestyle="-")
    plot_transition_boundary(axes, transition_points(frame, x_column, "mext_stable"),
                             color=MEXT_COLOR, linestyle="--")

    axes.set_xlabel(x_label, fontsize=AXIS_LABEL_FONT_SIZE, fontweight="bold")
    axes.set_ylabel(r"$\sum \alpha_{j\to 0,\mathrm{in}}$",
                    fontsize=AXIS_LABEL_FONT_SIZE, fontweight="bold")
    axes.set_xlim(*x_limit)
    axes.set_ylim(0.01, 0.99)
    axes.set_xticks(x_ticks)
    axes.set_yticks(Y_TICKS)
    axes.set_yticklabels([f"{int(round(value * 100))}%" for value in Y_TICKS])
    axes.tick_params(axis="both", which="major", labelsize=TICK_FONT_SIZE)
    axes.grid(True, alpha=0.3, zorder=2)

    divider = make_axes_locatable(axes)
    colorbar_axes = divider.append_axes("right", size=COLORBAR_SIZE, pad=COLORBAR_PAD)
    colorbar = figure.colorbar(scatter, cax=colorbar_axes)
    colorbar.set_label(COLORBAR_LABEL, rotation=270, labelpad=COLORBAR_LABEL_PAD,
                       fontsize=COLORBAR_LABEL_FONT_SIZE, fontweight="bold")
    colorbar.ax.tick_params(labelsize=COLORBAR_TICK_FONT_SIZE)
    ticks, labels = colorbar_ticks(observed_max)
    colorbar.set_ticks(ticks)
    colorbar.set_ticklabels(labels)

    axes.legend(
        handles=[
            Line2D([0], [0], color=SIMULATED_COLOR, linewidth=BOUNDARY_LINEWIDTH,
                   label="Simulated"),
            Line2D([0], [0], color=MEXT_COLOR, linewidth=MEXT_LINEWIDTH,
                   linestyle=MEXT_DASHES, label=r"$M_{\mathrm{ext}}$"),
        ],
        fontsize=LEGEND_FONT_SIZE, loc="lower left", bbox_to_anchor=(0.0, 1.015),
        ncol=2, frameon=True, handlelength=2.6, columnspacing=1.2, labelspacing=0.35,
    )

    figure.tight_layout(rect=LAYOUT_RECT)
    figure.savefig(output, dpi=RASTER_DPI)
    plt.close(figure)
    agreement = (frame["converged"] == frame["mext_stable"]).sum()
    print(f"[OK] {output}")
    print(f"     {len(unstable)} unstable cells, full-block share up to "
          f"{unstable['full_pct'].max():.2f}%, inflation up to "
          f"{unstable['inflation_pct'].max():.4f}%")
    print(f"     simulation/M_ext agreement: {agreement}/{len(frame)} "
          f"({100 * agreement / len(frame):.3f}%)")


def render_pattern(frame, output):
    """Load inflation against the strength of the instability.

    The x axis is the spectral radius of the linearized recurrence, which is the
    stability criterion itself, so the panel reads as cause against effect rather
    than one effect against another. Colour carries the share of full blocks, so
    the panel also shows which part of the unstable region saturates at all. The
    bracket encloses the cells that never fill a block.
    """
    unstable = frame.loc[~frame["converged"]]
    figure, axes = plt.subplots(figsize=FIGSIZE)
    axes.set_rasterization_zorder(2)

    observed_max = float(unstable["full_pct"].max())
    axes.axhline(INFLATION_CEILING, color=CEILING_COLOR, linestyle="--",
                 linewidth=CEILING_LINEWIDTH, zorder=3)
    scatter = axes.scatter(unstable["mext_rho"], unstable["inflation_pct"], s=3.0,
                           c=unstable["full_pct"], vmin=0.0, vmax=observed_max,
                           cmap=COLORMAP, alpha=0.75, linewidths=0,
                           rasterized=True, zorder=1)

    # Trace the upper edge of the cells that never fill a block, then drop to the
    # axis at the largest rho that still leaves every block short of the limit.
    unsaturated = unstable.loc[unstable["full_pct"] == 0]
    edges = np.linspace(unsaturated["mext_rho"].min(), unsaturated["mext_rho"].max(), 25)
    index = np.clip(np.digitize(unsaturated["mext_rho"].to_numpy(), edges) - 1, 0, len(edges) - 2)
    trace_x, trace_y = [], []
    for bin_index in range(len(edges) - 1):
        selected = unsaturated[index == bin_index]
        if selected.empty:
            continue
        trace_x.append((edges[bin_index] + edges[bin_index + 1]) / 2)
        trace_y.append(float(selected["inflation_pct"].max()))
    rho_max = float(unsaturated["mext_rho"].max())
    axes.plot(trace_x + [rho_max], trace_y + [0.0], color="black",
              linewidth=UNSATURATED_LINEWIDTH,
              solid_capstyle="round", zorder=5)
    axes.text(rho_max + 0.004, 1.35, "Unsaturated", fontsize=TICK_FONT_SIZE,
              fontweight="bold", ha="left", va="center", zorder=5)

    axes.set_xlabel(r"$\rho(\mathbf{M}_{\mathrm{ext}})$",
                    fontsize=AXIS_LABEL_FONT_SIZE, fontweight="bold")
    axes.set_ylabel("Load inflation (%)", fontsize=AXIS_LABEL_FONT_SIZE,
                    fontweight="bold")
    axes.set_xlim(0.995, 1.29)
    axes.set_ylim(-0.18, 7.0)
    axes.set_xticks([1.00, 1.05, 1.10, 1.15, 1.20, 1.25])
    axes.set_yticks([0, 2, 4, INFLATION_CEILING])
    axes.set_yticklabels(["0", "2", "4", f"{INFLATION_CEILING:.2f}"])
    axes.tick_params(axis="both", which="major", labelsize=TICK_FONT_SIZE)
    axes.grid(True, alpha=0.3, zorder=2)

    divider = make_axes_locatable(axes)
    colorbar_axes = divider.append_axes("right", size=COLORBAR_SIZE, pad=COLORBAR_PAD)
    colorbar = figure.colorbar(scatter, cax=colorbar_axes)
    colorbar.set_label(COLORBAR_LABEL, rotation=270, labelpad=COLORBAR_LABEL_PAD,
                       fontsize=COLORBAR_LABEL_FONT_SIZE, fontweight="bold")
    colorbar.ax.tick_params(labelsize=COLORBAR_TICK_FONT_SIZE)
    ticks, labels = colorbar_ticks(observed_max)
    colorbar.set_ticks(ticks)
    colorbar.set_ticklabels(labels)

    axes.legend(
        handles=[Line2D([0], [0], color=CEILING_COLOR, linewidth=CEILING_LINEWIDTH,
                        linestyle="--", label="Theoretical limit")],
        fontsize=LEGEND_FONT_SIZE, loc="lower left", bbox_to_anchor=(0.0, 1.015),
        ncol=1, frameon=True, handlelength=2.6, columnspacing=1.2, labelspacing=0.35,
    )

    figure.tight_layout(rect=LAYOUT_RECT)
    figure.savefig(output, dpi=RASTER_DPI)
    plt.close(figure)
    print(f"[OK] {output}")
    print(f"     rho in [{unstable['mext_rho'].min():.4f}, {unstable['mext_rho'].max():.4f}], "
          f"{len(unsaturated)} unstable cells never fill a block")
    print(f"     unsaturated region reaches rho = {rho_max:.4f} and "
          f"inflation = {unsaturated['inflation_pct'].max():.3f}%")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--output-dir", type=Path, default=Path("figures"))
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=True)

    epsilon_frame = load(arguments.data_dir / "convergence_results_Spike.csv", "epsilon_j0")
    delta_frame = load(arguments.data_dir / "convergence_results_delta_Spike.csv", "delta")

    render_map(epsilon_frame, "epsilon_j0", r"$\epsilon_{j0}$", (0.0, 16.0),
               [2.5, 5.0, 7.5, 10.0, 12.5, 16.0],
               arguments.output_dir / "over-correction-bubble-chart-spike.pdf")
    render_pattern(epsilon_frame,
                   arguments.output_dir / "over-correction-load-pattern-spike.pdf")
    render_map(delta_frame, "delta", r"$\delta$", (0.0, 0.125),
               [0.025, 0.05, 0.075, 0.1, 0.125],
               arguments.output_dir / "over-correction-bubble-chart-delta-spike.pdf")


if __name__ == "__main__":
    main()
