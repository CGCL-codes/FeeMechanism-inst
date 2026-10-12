"""Exact stability criterion for the compensated EIP-1559 controller (Appendix D).

The compensated update rule is

    x_i(t+1) = x_i(t) * ( 1 + delta_i * [ (L_i(t)-T_i)/T_i
                          - H_i * sum_d w_d (P_i(t)-P_i(t-d))/P_i(t) ] ),

which linearises to

    dx(t+1) = [I - delta (A + K)] dx(t) - delta sum_k w_k (B - K) dx(t-k),
    A_ii = Lambda_i^inst,  A_ij = Lambda_ij^inst,
    B_ii = Lambda_i^delay, B_ij = Lambda_ji^delay,  K = diag(H_i).

H_i = Lambda_i^delay = B_ii cancels the diagonal of every delayed block, so
Channel (III) disappears and the diagonal gain becomes Lambda_i^inst +
Lambda_i^delay. Setting every H_i to zero recovers the M_ext of the main text.
"""
import argparse
from pathlib import Path
from typing import Dict, Optional, Sequence

import numpy as np
import pandas as pd

from mext_criterion import (
    BASE_ELASTICITY,
    TARGET_LOAD,
    calculate_inbound_demand_matrix,
    delay_weights,
)


def channel_matrices(demand_matrix, lambda_matrix, epsilon_matrix, target_load):
    """Return (A, B): the instantaneous and delayed channel-coefficient matrices."""
    demand = np.asarray(demand_matrix, dtype=float) / float(target_load)
    lam = np.asarray(lambda_matrix, dtype=float)
    eps = np.asarray(epsilon_matrix, dtype=float)
    n = demand.shape[0]

    A = np.zeros((n, n))
    B = np.zeros((n, n))
    for i in range(n):
        # Channel (I): local plus source-side outbound.
        A[i, i] = sum(lam[i, j] * demand[i, j] for j in range(n))
        # Channel (II): destination-side outbound.
        for j in range(n):
            if j != i:
                A[i, j] = eps[i, j] * demand[i, j]
        # Channel (III): destination-side inbound.
        B[i, i] = sum(eps[j, i] * demand[j, i] for j in range(n) if j != i)
        # Channel (IV): source-side inbound.
        for j in range(n):
            if j != i:
                B[i, j] = lam[j, i] * demand[j, i]
    return A, B


def exact_compensation(B) -> np.ndarray:
    """H_i^* = Lambda_i^delay."""
    return np.diag(np.asarray(B, dtype=float)).copy()


def build_companion_matrix(
    demand_matrix,
    lambda_matrix,
    epsilon_matrix,
    delta,
    delay_weights,
    target_load,
    compensation=None,
) -> np.ndarray:
    A, B = channel_matrices(demand_matrix, lambda_matrix, epsilon_matrix, target_load)
    weights = np.asarray(delay_weights, dtype=float)
    if weights.ndim != 1 or len(weights) == 0:
        raise ValueError("delay_weights must be a non-empty one-dimensional sequence")
    if np.any(weights < 0.0) or not np.isclose(weights.sum(), 1.0):
        raise ValueError("delay_weights must be nonnegative and sum to one")

    n = A.shape[0]
    if compensation is None:
        compensation = np.zeros(n)
    H = np.broadcast_to(np.atleast_1d(np.asarray(compensation, dtype=float)), (n,))
    if np.any(H < 0.0):
        raise ValueError("compensation gains must be nonnegative")
    K = np.diag(H)
    d = np.broadcast_to(np.atleast_1d(np.asarray(delta, dtype=float)), (n,))[:, None]

    delay_count = len(weights)
    size = n * (delay_count + 1)
    companion = np.zeros((size, size))
    companion[:n, :n] = np.eye(n) - d * (A + K)
    for index, weight in enumerate(weights, start=1):
        companion[:n, index * n:(index + 1) * n] = -d * weight * (B - K)
    companion[n:, :-n] = np.eye(n * delay_count)
    return companion


def spectral_radius(matrix) -> float:
    return float(np.max(np.abs(np.linalg.eigvals(np.asarray(matrix, dtype=float)))))


def figure4_point(alpha: float, epsilon_j0: float, delta: float,
                  distribution: str = "spike", max_delay: int = 5,
                  num_shards: int = 3) -> Dict[str, object]:
    """The Figure 4 configuration: chain 0 receives only, peers stay symmetric."""
    lam = np.full((num_shards, num_shards), BASE_ELASTICITY)
    eps = np.full((num_shards, num_shards), BASE_ELASTICITY)
    np.fill_diagonal(eps, 0.0)
    for source in range(1, num_shards):
        eps[source, 0] = float(epsilon_j0)
    return {
        "demand_matrix": calculate_inbound_demand_matrix(alpha, num_shards),
        "lambda_matrix": lam,
        "epsilon_matrix": eps,
        "delta": float(delta),
        "delay_weights": delay_weights(distribution, max_delay),
        "target_load": TARGET_LOAD,
    }


def max_stable_delta(point: Dict[str, object], gamma: float = 1.0,
                     upper: float = 4.0, iterations: int = 80) -> float:
    """Largest delta with rho < 1, by bisection. Returns `upper` if never unstable."""
    A, B = channel_matrices(point["demand_matrix"], point["lambda_matrix"],
                            point["epsilon_matrix"], point["target_load"])
    H = gamma * exact_compensation(B)
    probe = dict(point)
    probe["compensation"] = H

    def stable(delta: float) -> bool:
        probe["delta"] = delta
        return spectral_radius(build_companion_matrix(**probe)) < 1.0

    if stable(upper):
        return upper
    low, high = 1e-7, upper
    for _ in range(iterations):
        mid = 0.5 * (low + high)
        if stable(mid):
            low = mid
        else:
            high = mid
    return low


MEXT_COLUMNS = ["mext_rho", "mext_stable", "classification_match"]


def annotate_dataframe(dataframe: pd.DataFrame, mode: str) -> pd.DataFrame:
    """Append the exact classification to a mitigation-sweep CSV."""
    mode_key = str(mode).strip().lower()
    if mode_key not in {"fig4a", "fig4c", "gamma", "deployed"}:
        raise ValueError("mode must be fig4a, fig4c, gamma, or deployed")
    parameter_column = "epsilon_j0" if mode_key == "fig4a" else "delta"
    required = {parameter_column, "alpha_inflow", "gamma", "converged"}
    if mode_key == "deployed":
        required.add("d_max")
    missing = sorted(required - set(dataframe.columns))
    if missing:
        raise ValueError("CSV is missing required columns: {}".format(", ".join(missing)))

    annotated = dataframe.drop(columns=MEXT_COLUMNS, errors="ignore").copy()
    rhos = []
    for row in annotated.itertuples(index=False):
        values = row._asdict()
        alpha = float(values["alpha_inflow"])
        gamma = float(values["gamma"])
        if mode_key == "fig4a":
            point = figure4_point(alpha, float(values["epsilon_j0"]), 0.125)
        elif mode_key == "deployed":
            point = figure4_point(alpha, 16.0, float(values["delta"]),
                                  max_delay=int(round(float(values["d_max"]))))
        else:
            point = figure4_point(alpha, 16.0, float(values["delta"]))
        A, B = channel_matrices(point["demand_matrix"], point["lambda_matrix"],
                                point["epsilon_matrix"], point["target_load"])
        point["compensation"] = gamma * exact_compensation(B)
        rhos.append(spectral_radius(build_companion_matrix(**point)))

    annotated["mext_rho"] = np.asarray(rhos, dtype=float)
    annotated["mext_stable"] = annotated["mext_rho"] < 1.0
    simulated = annotated["converged"].astype(str).str.strip().str.lower().map(
        {"true": True, "false": False}).astype(bool)
    annotated["classification_match"] = simulated == annotated["mext_stable"]
    return annotated


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append exact compensated-criterion classifications to a mitigation CSV.")
    parser.add_argument("mode", choices=["fig4a", "fig4c", "gamma", "deployed"])
    parser.add_argument("csv", nargs="+", type=Path)
    parser.add_argument("--in-place", action="store_true", required=True)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    for source in args.csv:
        annotated = annotate_dataframe(pd.read_csv(source), args.mode)
        temporary = source.with_name(source.name + ".tmp")
        annotated.to_csv(temporary, index=False)
        temporary.replace(source)
        matches = int(annotated["classification_match"].sum())
        print("{}: {}/{} classifications agree ({:.3%})".format(
            source, matches, len(annotated), matches / len(annotated)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
