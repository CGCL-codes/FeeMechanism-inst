"""The Figure 4a panel style, shared by every boundary map in the paper.

Figure 4a fixes the visual contract of a boundary map, and this module is the
one implementation of it:

  * converged cells are left white, so the stable region reads as empty and the
    map shows only what goes wrong;
  * an unstable cell is a bubble whose size encodes the realized load standard
    deviation and whose colour encodes the share of blocks that reach the gas
    limit, the quantity that matters for consensus rather than the load
    inflation that a bounded transaction pool caps;
  * the colour scale runs from zero to the largest share the panel itself
    reaches, so each panel spends its whole ramp on its own range;
  * the simulated boundary is solid dark red and the exact M_ext boundary is a
    blue dashed line on top of it;
  * every panel is one 6.2 x 5.2 inch canvas with the colour bar carved out of
    it, so LaTeX scales any two panels to the same height.

`render_panel` draws one panel. `transition_points` is Figure 4a's boundary
extractor: the midpoint of the first stable-to-unstable step in each column.
"""
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib import patheffects as pe
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from mpl_toolkits.axes_grid1 import make_axes_locatable

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

FIGSIZE = (6.2, 5.2)
RASTER_DPI = 200
AXIS_LABEL_FONT_SIZE = 21
TICK_FONT_SIZE = 17
COLORBAR_LABEL_FONT_SIZE = 19
COLORBAR_TICK_FONT_SIZE = 16
LEGEND_FONT_SIZE = 15
MINIMUM_BUBBLE_SIZE = 1.5
BUBBLE_SCALE = 1500.0

# The colour ramp of the whole family: a soft YlGnBu that starts just above
# white. Starting above white matters, because a converged cell carries no
# marker at all, so a ramp that began at white would make the unstable cells
# that never fill a block indistinguishable from the stable region. Swap the
# base name and the clip for a different ramp; every boundary panel follows.
COLORMAP = LinearSegmentedColormap.from_list(
    "YlGnBu_soft", plt.get_cmap("YlGnBu")(np.linspace(0.12, 0.88, 256)))
BUBBLE_ALPHA = 0.6

SIMULATED_COLOR = "darkred"
MEXT_COLOR = "#1764ab"
# The two boundaries agree almost everywhere, so equal weights draw as one
# chopped-up line. The simulated boundary is the wide band underneath and the
# M_ext boundary is the crisp dashed line laid on top of it. Both carry a white
# halo, which is what separates them from the pale end of the ramp.
BOUNDARY_LINEWIDTH = 6.4
MEXT_LINEWIDTH = 3.2
BOUNDARY_HALO_WIDTH = 3.0
# LaTeX places these panels at roughly a third of the text width, so a line
# drawn on the 6.2 inch canvas prints at about a third of its width here. The
# weights above are chosen to survive that reduction.
MEXT_DASHES = (0, (4.5, 2.2))

COLORBAR_SIZE = "4.5%"
COLORBAR_PAD = 0.13
COLORBAR_LABEL = "% full blocks"
COLORBAR_LABEL_PAD = 16
COLORBAR_CANDIDATE_TICKS = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90]
LAYOUT_RECT = [0.0, 0.0, 1.0, 0.895]

# The two x axes the boundary maps use.
EPSILON_AXIS = {"limits": (0.0, 16.0), "ticks": [2.5, 5.0, 7.5, 10.0, 12.5, 16.0]}
DELTA_AXIS = {"limits": (0.0, 0.125), "ticks": [0.025, 0.05, 0.075, 0.1, 0.125]}
Y_LIMITS = (0.01, 0.99)
Y_TICKS = np.arange(0.2, 1.0, 0.2)

REQUIRED_COLUMNS = {"load_std", "load_inflation", "converged", "full_block_fraction",
                    "mext_rho", "mext_stable"}


def boolean_series(series):
    if pd.api.types.is_bool_dtype(series):
        return series.fillna(False).astype(bool)
    if pd.api.types.is_numeric_dtype(series):
        return series.fillna(0).astype(float).ne(0.0)
    normalized = series.fillna("").astype(str).str.strip().str.lower()
    unknown = ~normalized.isin({"true", "false", "1", "0"})
    if unknown.any():
        raise ValueError(f"Unrecognized Boolean values: {sorted(normalized[unknown].unique())}")
    return normalized.isin({"true", "1"})


def prepare(frame, path, *, x_column, y_column):
    """Coerce the verdict columns and add the two percentage columns."""
    missing = sorted((REQUIRED_COLUMNS | {x_column, y_column}).difference(frame.columns))
    if missing:
        raise SystemExit(
            f"{path} is missing columns: {', '.join(missing)}. Rerun the sweep and "
            "annotate it with mext-criterion/mext_criterion.py.")
    frame = frame.copy()
    frame["converged"] = boolean_series(frame["converged"])
    frame["mext_stable"] = boolean_series(frame["mext_stable"])
    frame["full_pct"] = 100 * frame["full_block_fraction"]
    frame["inflation_pct"] = 100 * frame["load_inflation"]
    return frame


def transition_points(frame, x_column, y_column, state_column):
    """The midpoint of the first stable-to-unstable step in each column."""
    points = []
    for x_value, group in frame.groupby(x_column, sort=True):
        group = group.sort_values(y_column)
        ys = group[y_column].to_numpy(dtype=float)
        stable = group[state_column].to_numpy(dtype=bool)
        found = [
            (ys[index] + ys[index + 1]) / 2.0
            for index in range(len(group) - 1)
            if stable[index] and not stable[index + 1]
        ]
        if found:
            points.append((float(x_value), float(found[0])))
    return points


def draw_boundary(axes, points, *, color, linestyle, linewidth, zorder):
    """One boundary curve, haloed in white so it reads against the pale ramp."""
    if len(points) < 2:
        return False
    xs, ys = map(np.asarray, zip(*sorted(points)))
    smooth_x = np.linspace(xs.min(), xs.max(), 500)
    smooth_y = np.clip(np.interp(smooth_x, xs, ys), Y_LIMITS[0], Y_LIMITS[1])
    axes.plot(smooth_x, smooth_y, color=color, linewidth=linewidth,
              linestyle=linestyle, zorder=zorder, solid_capstyle="round",
              path_effects=[pe.Stroke(linewidth=linewidth + BOUNDARY_HALO_WIDTH,
                                      foreground="white", alpha=0.9), pe.Normal()])
    return True


def _plot_transition_boundary(axes, points, *, color, linestyle):
    solid = linestyle == "-"
    return draw_boundary(
        axes, points, color=color,
        linestyle="-" if solid else MEXT_DASHES,
        linewidth=BOUNDARY_LINEWIDTH if solid else MEXT_LINEWIDTH,
        zorder=4 if solid else 5)


def colorbar_ticks(vmax):
    """Round decades up to the panel's own maximum, which is always labelled.

    A decade is dropped when it would sit close enough to the maximum for the
    two labels to collide, so a panel with a small range simply carries fewer
    ticks.
    """
    if vmax <= 0:
        return [0.0], ["0"]
    kept = [tick for tick in COLORBAR_CANDIDATE_TICKS if tick <= 0.88 * vmax]
    if not kept:
        kept = [0]
    labels = [f"{tick:g}" for tick in kept] + [f"{vmax:.1f}"]
    return kept + [vmax], labels


def render_panel(
    frame,
    output_path,
    *,
    x_column,
    x_label,
    x_axis,
    y_column,
    y_label,
    colour_column="full_pct",
):
    """Draw one boundary map on Figure 4a's canvas."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    figure, axes = plt.subplots(figsize=FIGSIZE)
    axes.set_rasterization_zorder(2)

    unstable = frame.loc[~frame["converged"]]
    all_stable = unstable.empty
    scatter = None
    observed_max = 0.0
    # A panel whose unstable cells never fill a block has nothing for the colour
    # to encode. Its bubbles are drawn in the ramp's first colour and it carries
    # no colour bar, rather than a bar whose range is invented.
    flat = False
    if not all_stable:
        sizes = np.maximum(unstable["load_std"].to_numpy(dtype=float) * BUBBLE_SCALE,
                           MINIMUM_BUBBLE_SIZE)
        observed_max = float(unstable[colour_column].max())
        flat = observed_max <= 0.0
        scatter = axes.scatter(
            unstable[x_column], unstable[y_column],
            s=sizes, c=unstable[colour_column],
            vmin=0.0, vmax=observed_max if not flat else 1.0,
            alpha=BUBBLE_ALPHA, cmap=COLORMAP,
            edgecolors="none", linewidths=0, rasterized=True, zorder=1,
        )

    simulated_drawn = mext_drawn = False
    if not all_stable:
        simulated_drawn = _plot_transition_boundary(
            axes, transition_points(frame, x_column, y_column, "converged"),
            color=SIMULATED_COLOR, linestyle="-")
        mext_drawn = _plot_transition_boundary(
            axes, transition_points(frame, x_column, y_column, "mext_stable"),
            color=MEXT_COLOR, linestyle="--")

    axes.set_xlabel(x_label, fontsize=AXIS_LABEL_FONT_SIZE, fontweight="bold")
    axes.set_ylabel(y_label, fontsize=AXIS_LABEL_FONT_SIZE, fontweight="bold")
    axes.set_xlim(*x_axis["limits"])
    axes.set_ylim(*Y_LIMITS)
    axes.set_xticks(x_axis["ticks"])
    axes.set_yticks(Y_TICKS)
    axes.set_yticklabels([f"{int(round(value * 100))}%" for value in Y_TICKS])
    axes.tick_params(axis="both", which="major", labelsize=TICK_FONT_SIZE)
    axes.grid(True, alpha=0.3, zorder=2)

    # The colour bar is carved out of the same canvas whether or not it is drawn,
    # so an all-converged panel keeps the axes proportions of every other panel.
    divider = make_axes_locatable(axes)
    colorbar_axes = divider.append_axes("right", size=COLORBAR_SIZE, pad=COLORBAR_PAD)
    if scatter is None or flat:
        colorbar_axes.set_axis_off()
    else:
        bar = figure.colorbar(scatter, cax=colorbar_axes)
        bar.set_label(COLORBAR_LABEL, rotation=270, labelpad=COLORBAR_LABEL_PAD,
                      fontsize=COLORBAR_LABEL_FONT_SIZE, fontweight="bold")
        bar.ax.tick_params(labelsize=COLORBAR_TICK_FONT_SIZE)
        ticks, labels = colorbar_ticks(observed_max)
        bar.set_ticks(ticks)
        bar.set_ticklabels(labels)

    if not all_stable:
        axes.legend(
            handles=[
                Line2D([0], [0], color=SIMULATED_COLOR, linewidth=BOUNDARY_LINEWIDTH,
                       label="Simulated"),
                Line2D([0], [0], color=MEXT_COLOR, linewidth=MEXT_LINEWIDTH,
                       linestyle="--", label=r"$M_{\mathrm{ext}}$"),
            ],
            fontsize=LEGEND_FONT_SIZE, loc="lower left", bbox_to_anchor=(0.0, 1.015),
            ncol=2, frameon=True, handlelength=2.6, columnspacing=1.2, labelspacing=0.35,
        )

    figure.tight_layout(rect=LAYOUT_RECT)
    figure.savefig(output_path, dpi=RASTER_DPI)
    plt.close(figure)

    agreement = int((frame["converged"] == frame["mext_stable"]).sum())
    return {
        "path": output_path,
        "rows": int(len(frame)),
        "unstable": int(len(unstable)),
        "max_full_pct": observed_max,
        "max_inflation_pct": float(unstable["inflation_pct"].max()) if not all_stable else 0.0,
        "max_load_std": float(frame["load_std"].max()),
        "mext_agreement": agreement,
        "simulated_boundary": simulated_drawn,
        "mext_boundary": mext_drawn,
        "all_stable": all_stable,
        "never_full": flat,
    }


def report(result):
    path = result["path"]
    print(f"[OK] {path}")
    if result["all_stable"]:
        print(f"     every one of {result['rows']} configurations converges, "
              "so the panel carries no boundary and no colour")
    elif result["never_full"]:
        print(f"     {result['unstable']} unstable cells, none of which ever fills a "
              f"block, so the panel carries no colour bar; inflation up to "
              f"{result['max_inflation_pct']:.4f}%")
    else:
        print(f"     {result['unstable']} unstable cells, full-block share up to "
              f"{result['max_full_pct']:.2f}%, inflation up to "
              f"{result['max_inflation_pct']:.4f}%")
    print(f"     simulation/M_ext agreement: {result['mext_agreement']}/{result['rows']} "
          f"({100 * result['mext_agreement'] / result['rows']:.3f}%)")
