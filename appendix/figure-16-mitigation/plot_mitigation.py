"""Figure 16 -- the compensated controller applied to the Figure 4 system.

Panel (a): the largest stable update rate against the inbound ratio, under plain
EIP-1559 and under exact compensation, at the fixed elasticity 16 and spike
latency (d_max = 5). The dashed line is Ethereum's deployed rate 0.125.

Panel (b): the stable region in the (gamma, delta) plane at the hardest corner
alpha = 0.99, epsilon_j0 = 16, where gamma = H_i / Lambda_i^delay is the ratio
of the deployed gain (computed from estimated elasticities) to the actual
delayed coefficient, so gamma = 0 is plain EIP-1559 and gamma = 1 means the
estimate is exact.
"""
import sys
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

HERE = Path(__file__).resolve().parent
ARTIFACT_ROOT = HERE.parents[1]
sys.path.insert(0, str(ARTIFACT_ROOT / "mext-criterion"))

from mext_compensated import (channel_matrices, figure4_point,  # noqa: E402
                             max_stable_delta)

mpl.rcParams["pdf.compression"] = 9

DATA = HERE / "data"
FIGURES = HERE / "figures"
BASELINE_4B = (ARTIFACT_ROOT / "main" / "figure-04-stability-boundary" / "data"
               / "convergence_results_delta_Spike.csv")

DEPLOYED_DELTA = 0.125
FIXED_ELASTICITY = 16.0
CORNER_ALPHA = 0.99

PLAIN_COLOR = "#c81e1e"
COMPENSATED_COLOR = "#0b57d0"
STABLE_FILL = "#bcd2f5"
GRID_COLOR = "#d9d9d9"

AXIS_PT = 9
TICK_PT = 8
LEGEND_PT = 7.5


def boolean(series):
    return series.astype(str).str.strip().str.lower().map({"true": True, "false": False})


def simulated_boundary(csv_path, gamma_filter=None):
    """First delta on the 0.001 grid that fails to converge, per inbound ratio."""
    frame = pd.read_csv(csv_path)
    frame = frame.assign(stable=boolean(frame["converged"]))
    if gamma_filter is not None:
        frame = frame[np.isclose(frame["gamma"], gamma_filter)]
    alphas, boundaries = [], []
    for alpha, group in frame.groupby("alpha_inflow"):
        failed = group.loc[~group["stable"], "delta"]
        alphas.append(float(alpha))
        boundaries.append(float(failed.min()) if len(failed) else np.nan)
    order = np.argsort(alphas)
    return np.asarray(alphas)[order], np.asarray(boundaries)[order]


def exact_boundary(alphas, gamma):
    values = []
    for alpha in alphas:
        point = figure4_point(alpha, FIXED_ELASTICITY, DEPLOYED_DELTA)
        values.append(max_stable_delta(point, gamma=gamma, upper=1.5))
    return np.asarray(values)


def panel_a(axis):
    alphas = np.round(np.arange(0.01, 0.9901, 0.01), 4)
    plain = exact_boundary(alphas, gamma=0.0)
    compensated = exact_boundary(alphas, gamma=1.0)

    axis.fill_between(alphas, plain, compensated, color=STABLE_FILL, alpha=0.55,
                      linewidth=0, zorder=1, label="recovered by compensation")
    axis.plot(alphas, plain, color=PLAIN_COLOR, linewidth=1.9, zorder=3,
              label=r"EIP-1559 ($H_i=0$)")
    axis.plot(alphas, compensated, color=COMPENSATED_COLOR, linewidth=1.9, zorder=3,
              label=r"compensated ($H_i=\Lambda_i^{\rm delay}$)")
    axis.axhline(DEPLOYED_DELTA, color="black", linestyle=(0, (5, 3)), linewidth=1.1,
                 zorder=4)
    axis.text(0.40, DEPLOYED_DELTA * 1.13, r"$\delta=0.125$", fontsize=LEGEND_PT,
              zorder=6)

    # Cross-check against the nonlinear sweep of Figure 4c.
    sim_alpha, sim_plain = simulated_boundary(BASELINE_4B)
    axis.plot(sim_alpha[::6], sim_plain[::6], linestyle="none", marker="o",
              markersize=2.6, markerfacecolor="white", markeredgecolor=PLAIN_COLOR,
              markeredgewidth=0.8, zorder=5)

    axis.set_yscale("log")
    axis.set_xlim(0.0, 1.0)
    axis.set_ylim(0.012, 4.5)
    axis.set_xlabel("inbound ratio " r"$\sum_j\alpha_{j\to 0,\rm in}$", fontsize=AXIS_PT)
    axis.set_ylabel(r"max stable $\delta_0$", fontsize=AXIS_PT)
    axis.tick_params(labelsize=TICK_PT)
    axis.grid(True, which="both", color=GRID_COLOR, linewidth=0.6, zorder=0)
    axis.set_title("(a) restored safe regime", fontsize=AXIS_PT)
    handles = [
        Line2D([], [], color=PLAIN_COLOR, linewidth=1.9, label=r"EIP-1559"),
        Line2D([], [], color=COMPENSATED_COLOR, linewidth=1.9, label=r"compensated"),
        Patch(facecolor=STABLE_FILL, alpha=0.55, label="recovered"),
    ]
    axis.legend(handles=handles, fontsize=LEGEND_PT, loc="upper right", framealpha=0.92,
                borderpad=0.35, labelspacing=0.3, handlelength=1.5)


def panel_b(axis):
    frame = pd.read_csv(DATA / "mitigation_gamma_Spike.csv")
    frame = frame.assign(stable=boolean(frame["converged"]))
    gammas = np.sort(frame["gamma"].unique())
    deltas = np.sort(frame["delta"].unique())
    grid = (frame.pivot_table(index="delta", columns="gamma", values="stable")
            .reindex(index=deltas, columns=gammas).to_numpy(dtype=float))

    axis.contourf(gammas, deltas, grid, levels=[0.5, 1.5], colors=[STABLE_FILL],
                  alpha=0.85)
    axis.contour(gammas, deltas, grid, levels=[0.5], colors=[COMPENSATED_COLOR],
                 linewidths=1.6)
    axis.axvline(1.0, color="black", linestyle=(0, (5, 3)), linewidth=1.1)
    axis.axhline(DEPLOYED_DELTA, color=PLAIN_COLOR, linestyle=(0, (3, 2)),
                 linewidth=1.1)
    axis.text(0.97, 0.028, r"$\gamma=1$", fontsize=LEGEND_PT, va="bottom", ha="right")
    axis.text(0.03, DEPLOYED_DELTA + 0.004, r"$\delta=0.125$", fontsize=LEGEND_PT,
              color=PLAIN_COLOR, va="bottom")

    axis.set_xlim(gammas.min(), gammas.max())
    axis.set_ylim(deltas.min(), 0.2)
    axis.set_xlabel(r"estimation ratio $\gamma = H_i\,/\,\Lambda_i^{\rm delay}$",
                    fontsize=AXIS_PT)
    axis.set_ylabel(r"update rate $\delta_0$", fontsize=AXIS_PT)
    axis.tick_params(labelsize=TICK_PT)
    axis.grid(True, color=GRID_COLOR, linewidth=0.6, zorder=0)
    axis.set_title("(b) tolerance to estimation error", fontsize=AXIS_PT)
    axis.legend(handles=[Patch(facecolor=STABLE_FILL, alpha=0.85, label="converges")],
                fontsize=LEGEND_PT, loc="upper right", framealpha=0.92)


def report():
    mitigated_a = pd.read_csv(DATA / "mitigation_fig4a_Spike.csv")
    mitigated_b = pd.read_csv(DATA / "mitigation_fig4c_Spike.csv")
    baseline_a = pd.read_csv(ARTIFACT_ROOT / "main" / "figure-04-stability-boundary"
                             / "data" / "convergence_results_Spike.csv")
    baseline_b = pd.read_csv(BASELINE_4B)
    for label, baseline, mitigated in (("Figure 4a", baseline_a, mitigated_a),
                                       ("Figure 4c", baseline_b, mitigated_b)):
        base_bad = int((~boolean(baseline["converged"])).sum())
        mit_bad = int((~boolean(mitigated["converged"])).sum())
        print(f"{label}: nonconverged {base_bad}/{len(baseline)} -> "
              f"{mit_bad}/{len(mitigated)}; max inflation "
              f"{baseline['load_inflation'].max():.6f} -> "
              f"{mitigated['load_inflation'].max():.6f}; exact agreement "
              f"{int(mitigated['classification_match'].sum())}/{len(mitigated)}")

    corner = pd.read_csv(DATA / "mitigation_gamma_Spike.csv")
    corner = corner.assign(stable=boolean(corner["converged"]))
    window = corner[np.isclose(corner["delta"], DEPLOYED_DELTA) & corner["stable"]]["gamma"]
    print(f"gamma window at delta=0.125, alpha=0.99: "
          f"[{window.min():.3f}, {window.max():.3f}]")

    point = figure4_point(CORNER_ALPHA, FIXED_ELASTICITY, DEPLOYED_DELTA)
    A, B = channel_matrices(point["demand_matrix"], point["lambda_matrix"],
                            point["epsilon_matrix"], point["target_load"])
    print(f"corner chain 0: Lambda_inst={A[0,0]:.4f}, Lambda_delay={B[0,0]:.4f}, "
          f"bound H=0 {max_stable_delta(point, 0.0):.4f} -> "
          f"bound H=H* {max_stable_delta(point, 1.0):.4f}, "
          f"2/(inst+delay)={2/(A[0,0]+B[0,0]):.4f}")


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    figure, axes = plt.subplots(1, 2, figsize=(6.30, 2.91))
    panel_a(axes[0])
    panel_b(axes[1])
    figure.tight_layout(pad=0.45, w_pad=1.1)
    output = FIGURES / "mitigation-boundary.pdf"
    figure.savefig(output, bbox_inches="tight")
    plt.close(figure)
    print(f"wrote {output}")
    report()


if __name__ == "__main__":
    main()
