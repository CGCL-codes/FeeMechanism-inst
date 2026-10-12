"""Figures 7 and 8 -- the amplification indicators against channel intensity.

Reads the `kappa_scan_*.csv` files written by `run_kappa_sweeps.py` and draws the
four panels the paper prints. The x axis walks the swept elasticity together with
the inbound ratio, which the sweep maps onto it linearly, so one tick carries
both coordinates of the point.
"""
import argparse
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent

TITLE_FONTSIZE = 16
LABEL_FONTSIZE = 14
TICK_FONTSIZE = 12
LEGEND_FONTSIZE = 11
mpl.rcParams.update({
    "axes.titlesize": TITLE_FONTSIZE,
    "axes.labelsize": LABEL_FONTSIZE,
    "xtick.labelsize": TICK_FONTSIZE,
    "ytick.labelsize": TICK_FONTSIZE,
    "legend.fontsize": LEGEND_FONTSIZE,
    "pdf.fonttype": 42,
})

ORDER = ["Spike", "Uniform", "Bimodal"]
MARKERS = {"Spike": "o", "Uniform": "s", "Bimodal": "D"}

MODES = {
    "defense": {
        "directory": "defense-channel",
        "parameter": "epsilon_j0",
        "x_label": r"($\epsilon_{j0}$, $\sum\alpha_{j\to 0,\mathrm{in}}$) pairs",
        "outputs": ("fig7a_p90_defense.pdf", "fig7b_max_defense.pdf"),
    },
    "attack": {
        "directory": "attack-channel",
        "parameter": "lambda_j0",
        "x_label": r"($\lambda_{j0}$, $\sum\alpha_{j\to 0,\mathrm{in}}$) pairs",
        "outputs": ("fig8a_p90_attack.pdf", "fig8b_max_attack.pdf"),
    },
}


def prettify(axes):
    axes.grid(True, alpha=0.3)
    axes.tick_params(axis="both", labelsize=TICK_FONTSIZE)
    for spine in ("bottom", "left", "top", "right"):
        axes.spines[spine].set_linewidth(1.1)


def draw(frames, column, x_label, y_label, output_path, log_scale, linestyle):
    positions = np.arange(len(frames["Spike"]))
    tick_index = np.linspace(0, len(positions) - 1, 5).astype(int)
    reference = frames["Spike"]
    tick_labels = [f"({reference['parameter'].iloc[i]:.1f}, "
                   f"{reference['alpha_j0_in'].iloc[i]:.3f})" for i in tick_index]

    figure, axes = plt.subplots(figsize=(6.2, 3.4))
    for name in ORDER:
        axes.plot(positions, frames[name][column], linestyle=linestyle,
                  marker=MARKERS[name], markersize=6, linewidth=1.7, label=name)
    if log_scale:
        axes.set_yscale("log")
    axes.set_xticks(tick_index)
    axes.set_xticklabels(tick_labels)
    axes.set_xlabel(x_label, fontsize=LABEL_FONTSIZE)
    axes.set_ylabel(y_label, fontsize=LABEL_FONTSIZE)
    prettify(axes)
    axes.legend(loc="upper left", frameon=True)
    figure.tight_layout()
    figure.savefig(output_path)
    plt.close(figure)
    print(f"[OK] {output_path}")


def render(mode, output_dir):
    spec = MODES[mode]
    source = HERE / spec["directory"]
    frames = {}
    for name in ORDER:
        path = source / f"kappa_scan_{name}.csv"
        if not path.exists():
            raise SystemExit(f"missing {path}, run run_kappa_sweeps.py --mode {mode} first")
        frame = pd.read_csv(path).rename(columns={spec["parameter"]: "parameter"})
        frames[name] = frame.sort_values("parameter").reset_index(drop=True)
        print(f"[{mode}] {name}: p90 peaks at {frame['p90_kappa'].max():.2f} "
              f"at {spec['parameter']} = "
              f"{frame.loc[frame['p90_kappa'].idxmax(), 'parameter']:.1f}, "
              f"max peaks at {frame['max_kappa'].max():.4g}")
    percentile_output, maximum_output = spec["outputs"]
    draw(frames, "p90_kappa", spec["x_label"], r"90th-percentile $\kappa$",
         output_dir / percentile_output, log_scale=False, linestyle="-")
    draw(frames, "max_kappa", spec["x_label"], r"Max $\kappa$ (log scale)",
         output_dir / maximum_output, log_scale=True, linestyle="--")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=sorted(MODES) + ["all"], default="all")
    parser.add_argument("--output-dir", type=Path, default=HERE / "figures")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for mode in (sorted(MODES) if args.mode == "all" else [args.mode]):
        render(mode, args.output_dir)


if __name__ == "__main__":
    main()
