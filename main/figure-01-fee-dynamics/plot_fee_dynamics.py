from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D


ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "figures"

DATASETS = [
    {
        "csv": ROOT / "data/eth_2025-12-23/eth_fee_load_2025-12-23.csv",
        "title": "Ethereum (2025-12-23)",
    },
    {
        "csv": ROOT / "data/moonbeam_2025-03-21/moonbeam_fee_load_2025-03-21.csv",
        "title": "Moonbeam (2025-03-21)",
    },
]

TIME_OUTPUT = OUTPUT_DIR / "figure-01-top-fee-trajectories.pdf"
ANCHOR_OUTPUT = OUTPUT_DIR / "figure-01-bottom-price-anchor.pdf"

BLUE = "#0077BB"
RED = "#CC3311"
TOP_YLIM = (0.8, 300)
TOP_YTICKS = [1, 10, 100]
ANCHOR_LIM = (0.9, 16)
ANCHOR_TICKS = [1, 2, 5, 10]

matplotlib.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
        "font.size": 10.5,
        "axes.titlesize": 12.5,
        "axes.labelsize": 11.5,
        "xtick.labelsize": 10,
        "ytick.labelsize": 10,
        "legend.fontsize": 11,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def load_df(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp"]).sort_values("timestamp")
    df = df[
        (df["base_fee_gwei"] > 0) & (df["effective_gas_price_gwei"] > 0)
    ].copy()

    day = df["timestamp"].dt.floor("D")
    df["hour"] = (df["timestamp"] - day).dt.total_seconds() / 3600.0

    base_min = float(df["base_fee_gwei"].min())
    df["base_ratio"] = df["base_fee_gwei"] / base_min
    df["price_ratio"] = df["effective_gas_price_gwei"] / base_min
    return df


def rolling_median_5min(df: pd.DataFrame) -> np.ndarray:
    prices = df.set_index("timestamp")["price_ratio"]
    return prices.rolling("5min", center=True, min_periods=1).median().to_numpy()


def high_load_subset(df: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    threshold = float(df["load"].quantile(0.9))
    return df[df["load"] >= threshold].copy(), threshold


def anchor_correlation(df: pd.DataFrame) -> float:
    return float(
        np.corrcoef(
            np.log(df["base_fee_gwei"]),
            np.log(df["effective_gas_price_gwei"]),
        )[0, 1]
    )


def style_time_axis(ax: plt.Axes, show_ylabel: bool) -> None:
    ax.set_yscale("log")
    ax.set_ylim(*TOP_YLIM)
    ax.set_yticks(TOP_YTICKS)
    ax.set_yticklabels([r"$1\times$", r"$10\times$", r"$100\times$"])
    ax.set_xlim(0, 24)
    ax.set_xticks([0, 6, 12, 18, 24])
    ax.set_xlabel("Hour of day (UTC)")
    if show_ylabel:
        ax.set_ylabel("Normalized fee")
    ax.grid(which="major", alpha=0.28)
    ax.grid(which="minor", alpha=0.09)


def style_anchor_axis(ax: plt.Axes, show_ylabel: bool) -> None:
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlim(*ANCHOR_LIM)
    ax.set_ylim(*ANCHOR_LIM)
    ax.set_xticks(ANCHOR_TICKS)
    ax.set_yticks(ANCHOR_TICKS)
    tick_labels = [r"$1\times$", r"$2\times$", r"$5\times$", r"$10\times$"]
    ax.set_xticklabels(tick_labels)
    ax.set_yticklabels(tick_labels)
    ax.set_xlabel("Base fee $B$")
    if show_ylabel:
        ax.set_ylabel("Effective gas price $P$")
    ax.grid(which="major", alpha=0.28)
    ax.grid(which="minor", alpha=0.09)


def plot_time_figure(frames: list[pd.DataFrame]) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.05))
    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.20, top=0.78, wspace=0.21)

    legend_handles = None
    for col, (cfg, df) in enumerate(zip(DATASETS, frames)):
        ax = axes[col]
        ax.scatter(
            df["hour"],
            df["price_ratio"],
            s=3.0,
            color=RED,
            alpha=0.38,
            linewidths=0,
            rasterized=True,
            zorder=1,
        )
        (h_base,) = ax.plot(
            df["hour"],
            df["base_ratio"],
            color=BLUE,
            lw=1.8,
            label=r"base fee $B$",
            zorder=3,
        )
        (h_median,) = ax.plot(
            df["hour"],
            rolling_median_5min(df),
            color="black",
            lw=1.0,
            ls=(0, (4, 2)),
            alpha=0.92,
            label=r"5-min median of $P$",
            zorder=4,
        )
        # The scatter marker is 3 pt in the panel, illegible in a legend key, so
        # the legend uses an opaque proxy dot instead.
        h_points = Line2D(
            [],
            [],
            marker="o",
            ms=7.0,
            mfc=RED,
            mec="none",
            ls="none",
            label=r"effective gas price $P$",
        )
        legend_handles = [h_base, h_points, h_median]

        ax.set_title(cfg["title"], pad=6)
        style_time_axis(ax, show_ylabel=(col == 0))

    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=3,
        fontsize=13.0,
        frameon=False,
        bbox_to_anchor=(0.5, 0.985),
        handlelength=1.8,
        handletextpad=0.35,
        columnspacing=0.8,
    )
    fig.savefig(TIME_OUTPUT)
    plt.close(fig)


def plot_anchor_figure(frames: list[pd.DataFrame]) -> list[tuple[str, int, float, float]]:
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.15))
    fig.subplots_adjust(left=0.105, right=0.985, bottom=0.20, top=0.84, wspace=0.21)

    diagnostics = []
    diagonal = np.geomspace(ANCHOR_LIM[0], ANCHOR_LIM[1], 100)

    for col, (cfg, df) in enumerate(zip(DATASETS, frames)):
        high, threshold = high_load_subset(df)
        rho = anchor_correlation(high)
        ax = axes[col]

        ax.scatter(
            high["base_ratio"],
            high["price_ratio"],
            s=11,
            color=RED,
            alpha=0.34,
            linewidths=0,
            rasterized=True,
            zorder=2,
        )
        ax.plot(diagonal, diagonal, color="0.35", lw=1.15, ls="--", zorder=1)
        ax.text(
            8.1,
            8.55,
            r"$P=B$",
            ha="center",
            va="center",
            fontsize=9.5,
            color="0.35",
            rotation=28,
            bbox=dict(fc="white", ec="none", alpha=0.76, pad=0.4),
        )
        ax.text(
            0.045,
            0.94,
            rf"$\rho_{{\mathrm{{anchor}}}}={rho:.3f}$",
            transform=ax.transAxes,
            va="top",
            fontsize=11,
            bbox=dict(fc="white", ec="0.75", alpha=0.90, pad=2.5),
        )
        ax.set_title(cfg["title"], pad=6)
        style_anchor_axis(ax, show_ylabel=(col == 0))
        diagnostics.append((cfg["title"], len(high), threshold, rho))

    fig.savefig(ANCHOR_OUTPUT)
    plt.close(fig)
    return diagnostics


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    frames = [load_df(cfg["csv"]) for cfg in DATASETS]

    plot_time_figure(frames)
    diagnostics = plot_anchor_figure(frames)

    for title, n_high, threshold, rho in diagnostics:
        print(
            f"{title}: top-decile n={n_high}, load threshold={threshold:.6f}, "
            f"rho_anchor={rho:.6f}"
        )
    for title, df in zip((cfg["title"] for cfg in DATASETS), frames):
        clipped = int((df["price_ratio"] > TOP_YLIM[1]).sum())
        print(f"{title}: temporal observations above {TOP_YLIM[1]:g}x={clipped}")
    print(f"Saved {TIME_OUTPUT}")
    print(f"Saved {ANCHOR_OUTPUT}")


if __name__ == "__main__":
    main()
