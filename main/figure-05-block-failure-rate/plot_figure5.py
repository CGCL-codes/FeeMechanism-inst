"""Figure 5 -- block failure rate at each load inflation level, two stacked panels.

Section 7.3. Every sample of the Q = 20 sweep is drawn, coloured by its share of
full blocks on the Figure 4 scale. The failure rate of a sample is its load
histogram contracted with the chain's load-to-failure mapping of Appendix C.1.
Stars mark the deployed configurations of Table 2, and the two panels share the
inflation axis.
"""
import argparse
import csv
import glob
import math
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

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

HERE = Path(__file__).resolve().parent

AXIS_LABEL_FONT_SIZE = 21
TICK_FONT_SIZE = 16
COLORBAR_LABEL_FONT_SIZE = 19
COLORBAR_TICK_FONT_SIZE = 15
LEGEND_FONT_SIZE = 15
ANNOTATION_FONT_SIZE = 18

DELTA = 0.125
INFLATION_CEILING = 100 * (-math.log(1 - DELTA**2)
                           / math.log((1 + DELTA) / (1 - DELTA)))
BIN = [f"bin{index}" for index in range(100)]
# The sweep histogram and the mapping of Appendix C.1 share the same grid, one
# hundred bins of width 0.01, so the two contract directly.
FULL_BIN = 99
POST_STEPS = 50_000
LEVELS_PER_PERCENT = 10
TOP_LEVEL = 62                     # the 6.2% level, the last one Section 7.3 reports
PER_LEVEL = 100                    # configurations kept per 0.1% level
SUBSAMPLE_SEED = 801

# The on-chain baselines of Section 7.3.
BASELINE = {"hub": 0.166, "osmo": 5.25}
PANEL_TITLE = {"hub": "Cosmos Hub", "osmo": "Osmosis"}
# The deployed trajectories of Section 7.3, and the inflation each one realizes.
DEPLOYED = {"hub": ("hub_final_trace.csv", 0.85), "osmo": ("osmo_final_trace.csv", 1.88)}


def load_sweep(sweep_dir, mapping):
    frames = [pd.read_csv(path) for path in sorted(glob.glob(str(sweep_dir / "random_q20_*.csv")))]
    if not frames:
        raise SystemExit(f"no random_q20_*.csv under {sweep_dir}")
    samples = pd.concat(frames, ignore_index=True)
    samples = samples[(samples.inflation_pct >= 0) & (samples.inflation_pct <= 6.5)].copy()
    samples["level"] = (samples.inflation_pct * LEVELS_PER_PERCENT).astype(int)

    # Exactly 100 configurations per 0.1% level, as reported in Section 7.3.
    generator = np.random.default_rng(SUBSAMPLE_SEED)
    kept = []
    for level, group in samples.groupby("level"):
        if level > TOP_LEVEL:
            continue
        take = min(PER_LEVEL, len(group))
        kept.append(group.iloc[generator.permutation(len(group))[:take]])
    samples = pd.concat(kept, ignore_index=True)

    counts = samples[BIN].to_numpy(float)
    samples["full_pct"] = 100 * counts[:, FULL_BIN] / POST_STEPS
    for chain in ("hub", "osmo"):
        # NumPy raises a spurious floating-point warning from the BLAS path of
        # matmul on some builds. Every operand here is a finite count.
        with np.errstate(all="ignore"):
            samples[chain] = counts @ mapping[f"F_{chain}"].to_numpy() / POST_STEPS * 100
    return samples


def star_for(chain, trace_path, inflation, mapping):
    """Contract a deployed trajectory's load histogram with the chain's mapping."""
    loads = np.clip(np.array(
        [float(row["load"]) for row in csv.DictReader(open(trace_path))]), 0, 1)
    edges = list(np.round(np.arange(0, 1.0, 0.01), 4)) + [1.01]
    counts = np.array([((loads >= low) & (loads < high)).sum()
                       for low, high in zip(edges[:-1], edges[1:])], float)
    return inflation, counts @ mapping[f"F_{chain}"].to_numpy() / len(loads) * 100


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--mapping", type=Path, default=HERE / "data" / "F_100bin.csv")
    parser.add_argument("--sweep-dir", type=Path,
                        default=HERE / "simulation-inflation-levels" / "data")
    parser.add_argument("--trace-dir", type=Path,
                        default=HERE / "simulation-inflation-levels" / "traces")
    parser.add_argument("--output-dir", type=Path, default=HERE / "figures")
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    mapping = pd.read_csv(args.mapping)
    samples = load_sweep(args.sweep_dir, mapping)
    ceiling = float(samples.full_pct.max())
    stars = {chain: star_for(chain, args.trace_dir / trace, inflation, mapping)
             for chain, (trace, inflation) in DEPLOYED.items()}

    print(f"{len(samples)} samples over {samples.level.nunique()} levels, "
          f"full-block share up to {ceiling:.2f}%")
    for chain in ("hub", "osmo"):
        inflation, rate = stars[chain]
        print(f"{PANEL_TITLE[chain]}")
        print(f"  deployed: inflation {inflation:.2f}%, failure {rate:.2f}% "
              f"({rate / BASELINE[chain]:.1f}x the on-chain {BASELINE[chain]}%)")
        top = samples.loc[samples.level == TOP_LEVEL, chain]
        print(f"  at the {INFLATION_CEILING:.2f}% bound: failure {top.median():.2f}% "
              f"({top.median() / BASELINE[chain]:.1f}x)")
        at_one = samples.loc[samples.level == LEVELS_PER_PERCENT, chain]
        print(f"  at 1% inflation: failure {at_one.median():.2f}% "
              f"({at_one.median() / BASELINE[chain]:.1f}x)")
        zero = samples.loc[samples.level == 0, chain]
        print(f"  at zero inflation: failure {zero.median():.2f}%")

    figure, axes = plt.subplots(2, 1, figsize=(7.4, 4.9), sharex=True,
                               gridspec_kw={"hspace": 0.08})
    scatter = None
    for axis, chain in zip(axes, ("hub", "osmo")):
        axis.set_rasterization_zorder(2)
        scatter = axis.scatter(
            samples.inflation_pct, samples[chain], s=7.0, c=samples.full_pct,
            vmin=0.0, vmax=ceiling, alpha=0.5, cmap="viridis",
            edgecolors="none", linewidths=0, rasterized=True, zorder=1)
        inflation, rate = stars[chain]
        axis.scatter([inflation], [rate], marker="*", s=580, facecolor="white",
                     edgecolor="black", linewidth=1.6, zorder=5)
        axis.text(0.985, 0.06, PANEL_TITLE[chain], transform=axis.transAxes,
                  ha="right", va="bottom", fontsize=ANNOTATION_FONT_SIZE,
                  fontweight="bold")
        axis.tick_params(axis="both", which="major", labelsize=TICK_FONT_SIZE)
        axis.grid(True, alpha=0.3, zorder=0)
        axis.set_xlim(-0.15, 6.45)

    axes[0].set_ylim(-0.4, 9.9)
    axes[0].set_yticks([0, 3, 6, 9])
    axes[1].set_ylim(7.4, 21.2)
    axes[1].set_yticks([8, 12, 16, 20])
    axes[1].set_xticks([0, 1, 2, 3, 4, 5, 6])
    axes[1].set_xlabel("load inflation (%)", fontsize=AXIS_LABEL_FONT_SIZE,
                       fontweight="bold")
    figure.supylabel("block failure rate (%)", x=0.035,
                     fontsize=AXIS_LABEL_FONT_SIZE, fontweight="bold")

    colorbar = figure.colorbar(scatter, ax=axes, pad=0.012, fraction=0.028)
    colorbar.set_label("% full blocks", rotation=270, labelpad=13,
                       fontsize=COLORBAR_LABEL_FONT_SIZE, fontweight="bold")
    colorbar.ax.tick_params(labelsize=COLORBAR_TICK_FONT_SIZE)
    colorbar.set_ticks([0, 10, 20, 30, 40, ceiling])
    colorbar.set_ticklabels(["0", "10", "20", "30", "40", f"{ceiling:.1f}"])

    axes[0].legend(
        handles=[Line2D([0], [0], marker="*", linestyle="none", markersize=15,
                        markerfacecolor="white", markeredgecolor="black",
                        markeredgewidth=1.6, label="Deployed")],
        fontsize=LEGEND_FONT_SIZE, loc="upper left", frameon=True,
        handletextpad=0.4, borderpad=0.35)

    for suffix in ("pdf", "png"):
        output = args.output_dir / f"fig_failure_rate_combined.{suffix}"
        figure.savefig(output, dpi=200, bbox_inches="tight")
        print(f"[OK] {output}")
    plt.close(figure)


if __name__ == "__main__":
    main()
