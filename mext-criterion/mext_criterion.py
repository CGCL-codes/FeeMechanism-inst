import argparse
from pathlib import Path
from typing import Dict, Iterable, Optional, Sequence, Union

import numpy as np
import pandas as pd


G_MAX = 2_000_000.0
TARGET_LOAD = G_MAX / 2.0
BASE_ELASTICITY = 1.5
FIXED_DELTA = 0.125
FIXED_EPSILON_J0 = 16.0

DELAY_DISTRIBUTIONS = {
    "spike": np.array([0.0, 0.0, 0.0, 0.0, 1.0]),
    "uniform": np.array([0.2, 0.2, 0.2, 0.2, 0.2]),
    "bimodal": np.array([0.4, 0.0, 0.2, 0.0, 0.4]),
}

MEXT_COLUMNS = ["mext_rho", "mext_stable", "classification_match"]


def calculate_demand_matrix(alpha_inflow: float) -> np.ndarray:
    return calculate_inbound_demand_matrix(alpha_inflow, num_shards=3)


def calculate_inbound_demand_matrix(alpha_inflow: float, num_shards: int) -> np.ndarray:
    alpha = float(alpha_inflow)
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha_inflow must lie in [0, 1]")
    chain_count = int(num_shards)
    if chain_count < 3:
        raise ValueError("num_shards must be at least 3")

    matrix = np.zeros((chain_count, chain_count), dtype=float)
    diagonal = (1.0 - alpha) * TARGET_LOAD
    np.fill_diagonal(matrix, diagonal)
    inbound_each = alpha * TARGET_LOAD / float(chain_count - 1)
    between_other_chains = alpha * TARGET_LOAD / float(2 * (chain_count - 1))
    for source in range(1, chain_count):
        matrix[source, 0] = inbound_each
        for destination in range(1, chain_count):
            if destination != source:
                matrix[source, destination] = between_other_chains
    return matrix


def calculate_outbound_demand_matrix(alpha_outflow: float) -> np.ndarray:
    alpha = float(alpha_outflow)
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha_outflow must lie in [0, 1]")
    diagonal = (1.0 - alpha) * TARGET_LOAD
    return np.array(
        [
            [diagonal, alpha * TARGET_LOAD / 2.0, alpha * TARGET_LOAD / 2.0],
            [0.0, diagonal, alpha * TARGET_LOAD / 4.0],
            [0.0, alpha * TARGET_LOAD / 4.0, diagonal],
        ],
        dtype=float,
    )


def delay_weights(distribution: str, max_delay: int) -> np.ndarray:
    distribution_key = str(distribution).strip().lower()
    delay = int(max_delay)
    if delay < 1:
        raise ValueError("max_delay must be at least 1")
    if distribution_key == "spike":
        weights = np.zeros(delay, dtype=float)
        weights[-1] = 1.0
        return weights
    if distribution_key == "uniform":
        if delay == 3:
            return np.array([0.33, 0.33, 0.34], dtype=float)
        if delay == 5:
            return np.array([0.2] * 5, dtype=float)
        if delay == 7:
            return np.array([0.14, 0.14, 0.14, 0.14, 0.14, 0.15, 0.15], dtype=float)
        if delay == 10:
            return np.array([0.1] * 10, dtype=float)
    if distribution_key == "bimodal" and delay == 5:
        return np.array([0.4, 0.0, 0.2, 0.0, 0.4], dtype=float)
    raise ValueError(
        "unsupported {} distribution with max_delay={}".format(distribution, delay)
    )


def reconstruct_appendix_point(
    experiment: str,
    parameter: float,
    alpha: float,
    distribution: str,
    max_delay: Optional[int] = None,
    num_shards: Optional[int] = None,
) -> Dict[str, object]:
    experiment_key = str(experiment).strip().lower()
    if experiment_key not in {"fig10", "fig11", "fig12", "fig13", "fig14"}:
        raise ValueError("appendix experiment must be fig9-top, fig9-bottom, fig10, fig12, or fig13")

    point_parameter = float(parameter)
    point_alpha = float(alpha)
    if not 0.0 <= point_parameter <= 16.0:
        raise ValueError("parameter must lie in [0, 16]")
    if not 0.0 <= point_alpha <= 1.0:
        raise ValueError("alpha must lie in [0, 1]")

    if experiment_key == "fig13" and max_delay is None:
        raise ValueError("fig12 requires explicit max_delay metadata")
    default_delays = {"fig10": 5, "fig11": 5, "fig12": 1, "fig14": 5}
    point_delay = int(max_delay if max_delay is not None else default_delays[experiment_key])
    point_shards = int(num_shards if num_shards is not None else 3)

    distribution_key = str(distribution).strip().lower()
    if experiment_key in {"fig10", "fig11"}:
        if point_shards != 3 or point_delay != 5:
            raise ValueError("fig9-top and fig9-bottom require three chains and max_delay=5")
        if distribution_key not in {"spike", "uniform", "bimodal"}:
            raise ValueError("fig9-top and fig9-bottom require spike, uniform, or bimodal delay")
    elif experiment_key == "fig12":
        if point_shards != 3 or point_delay != 1 or distribution_key != "spike":
            raise ValueError("fig10 requires three chains and spike max_delay=1")
    elif experiment_key == "fig13":
        if point_shards != 3 or point_delay not in {5, 7, 10}:
            raise ValueError("fig12 requires three chains and max_delay=5, 7, or 10")
        if distribution_key not in {"spike", "uniform"}:
            raise ValueError("fig12 requires spike or uniform delay")
    elif experiment_key == "fig14":
        if point_shards not in {5, 7, 10} or point_delay != 5 or distribution_key != "spike":
            raise ValueError("fig13 requires spike max_delay=5 and 5, 7, or 10 chains")

    lambda_matrix = np.full((point_shards, point_shards), BASE_ELASTICITY, dtype=float)
    epsilon_matrix = np.full((point_shards, point_shards), BASE_ELASTICITY, dtype=float)
    np.fill_diagonal(epsilon_matrix, 0.0)

    if experiment_key == "fig10":
        for source in range(1, point_shards):
            lambda_matrix[source, 0] = point_parameter
        demand_matrix = calculate_inbound_demand_matrix(point_alpha, point_shards)
    elif experiment_key in {"fig11", "fig12"}:
        epsilon_matrix[0, 1] = point_parameter
        epsilon_matrix[0, 2] = point_parameter
        demand_matrix = calculate_outbound_demand_matrix(point_alpha)
    else:
        for source in range(1, point_shards):
            epsilon_matrix[source, 0] = point_parameter
        demand_matrix = calculate_inbound_demand_matrix(point_alpha, point_shards)

    return {
        "demand_matrix": demand_matrix,
        "lambda_matrix": lambda_matrix,
        "epsilon_matrix": epsilon_matrix,
        "delta": FIXED_DELTA,
        "delay_weights": delay_weights(distribution, point_delay),
        "target_load": TARGET_LOAD,
    }


def reconstruct_point(
    experiment: str,
    alpha_inflow: float,
    distribution: str = "Spike",
    epsilon_j0: Optional[float] = None,
    delta: Optional[float] = None,
) -> Dict[str, object]:
    experiment_key = experiment.lower()
    distribution_key = str(distribution).strip().lower()
    if distribution_key not in DELAY_DISTRIBUTIONS:
        raise ValueError(
            "unknown delay distribution {!r}; expected one of {}".format(
                distribution, ", ".join(sorted(DELAY_DISTRIBUTIONS))
            )
        )

    lambda_matrix = np.full((3, 3), BASE_ELASTICITY, dtype=float)
    epsilon_matrix = np.full((3, 3), BASE_ELASTICITY, dtype=float)
    np.fill_diagonal(epsilon_matrix, 0.0)

    if experiment_key == "fig6":
        if epsilon_j0 is None:
            raise ValueError("fig4a rows require epsilon_j0")
        point_delta = FIXED_DELTA
        inbound_epsilon = float(epsilon_j0)
    elif experiment_key == "fig7":
        if delta is None:
            raise ValueError("fig4c rows require delta")
        point_delta = float(delta)
        inbound_epsilon = FIXED_EPSILON_J0
    else:
        raise ValueError("experiment must be 'fig4a' or 'fig4c'")

    epsilon_matrix[1, 0] = inbound_epsilon
    epsilon_matrix[2, 0] = inbound_epsilon

    return {
        "demand_matrix": calculate_demand_matrix(alpha_inflow),
        "lambda_matrix": lambda_matrix,
        "epsilon_matrix": epsilon_matrix,
        "delta": point_delta,
        "delay_weights": DELAY_DISTRIBUTIONS[distribution_key].copy(),
        "target_load": TARGET_LOAD,
    }


def build_companion_matrix(
    demand_matrix: np.ndarray,
    lambda_matrix: np.ndarray,
    epsilon_matrix: np.ndarray,
    delta: float,
    delay_weights: Sequence[float],
    target_load: float,
) -> np.ndarray:
    demand = np.asarray(demand_matrix, dtype=float)
    source_elasticity = np.asarray(lambda_matrix, dtype=float)
    destination_elasticity = np.asarray(epsilon_matrix, dtype=float)
    weights = np.asarray(delay_weights, dtype=float)

    if demand.ndim != 2 or demand.shape[0] != demand.shape[1]:
        raise ValueError("demand_matrix must be square")
    if source_elasticity.shape != demand.shape or destination_elasticity.shape != demand.shape:
        raise ValueError("elasticity matrices must match demand_matrix")
    if weights.ndim != 1 or len(weights) == 0:
        raise ValueError("delay_weights must be a non-empty one-dimensional sequence")
    if np.any(weights < 0.0) or not np.isclose(weights.sum(), 1.0):
        raise ValueError("delay_weights must be nonnegative and sum to one")
    if float(target_load) <= 0.0:
        raise ValueError("target_load must be positive")

    chain_count = demand.shape[0]
    delay_count = len(weights)
    normalized_demand = demand / float(target_load)
    point_delta = float(delta)

    a0 = np.zeros((chain_count, chain_count), dtype=float)
    for i in range(chain_count):
        instantaneous_self = source_elasticity[i, i] * normalized_demand[i, i]
        instantaneous_self += sum(
            source_elasticity[i, j] * normalized_demand[i, j]
            for j in range(chain_count)
            if j != i
        )
        a0[i, i] = 1.0 - point_delta * instantaneous_self
        for j in range(chain_count):
            if j != i:
                a0[i, j] = (
                    -point_delta
                    * destination_elasticity[i, j]
                    * normalized_demand[i, j]
                )

    delayed_base = np.zeros((chain_count, chain_count), dtype=float)
    for i in range(chain_count):
        delayed_base[i, i] = sum(
            destination_elasticity[j, i] * normalized_demand[j, i]
            for j in range(chain_count)
            if j != i
        )
        for j in range(chain_count):
            if j != i:
                delayed_base[i, j] = (
                    source_elasticity[j, i] * normalized_demand[j, i]
                )

    block_size = chain_count * (delay_count + 1)
    companion = np.zeros((block_size, block_size), dtype=float)
    companion[:chain_count, :chain_count] = a0
    for delay_index, weight in enumerate(weights, start=1):
        column_start = delay_index * chain_count
        companion[
            :chain_count, column_start : column_start + chain_count
        ] = -point_delta * weight * delayed_base

    companion[chain_count:, :-chain_count] = np.eye(chain_count * delay_count)
    return companion


def spectral_radius(matrix: np.ndarray) -> float:
    eigenvalues = np.linalg.eigvals(np.asarray(matrix, dtype=float))
    return float(np.max(np.abs(eigenvalues)))


def is_stable(matrix: np.ndarray) -> bool:
    return spectral_radius(matrix) < 1.0


def _boolean_series(series: pd.Series) -> pd.Series:
    if pd.api.types.is_bool_dtype(series):
        return series.astype(bool)

    normalized = series.astype(str).str.strip().str.lower()
    mapping = {"true": True, "false": False, "1": True, "0": False}
    unknown = sorted(set(normalized) - set(mapping))
    if unknown:
        raise ValueError("unrecognized converged values: {}".format(unknown))
    return normalized.map(mapping).astype(bool)


def annotate_dataframe(
    dataframe: pd.DataFrame,
    experiment: str,
    max_delay: Optional[int] = None,
    num_shards: Optional[int] = None,
) -> pd.DataFrame:
    experiment_key = experiment.lower()
    if experiment_key in {"fig6", "fig7"}:
        alpha_column = "alpha_inflow"
        parameter_column = "epsilon_j0" if experiment_key == "fig6" else "delta"
    else:
        parameter_columns = {
            "fig10": "lambda_j0",
            "fig11": "epsilon_0j",
            "fig12": "epsilon_0j",
            "fig13": "epsilon_j0",
            "fig14": "epsilon_j0",
        }
        alpha_columns = {
            "fig10": "alpha_inflow",
            "fig11": "alpha_outflow",
            "fig12": "alpha_outflow",
            "fig13": "alpha_inflow",
            "fig14": "alpha_inflow",
        }
        if experiment_key not in parameter_columns:
            raise ValueError("experiment must be fig4a, fig4c, fig9-top, fig9-bottom, fig10, fig12, or fig13")
        parameter_column = parameter_columns[experiment_key]
        alpha_column = alpha_columns[experiment_key]

    required = {alpha_column, parameter_column, "distribution", "converged"}
    if experiment_key == "fig14" and num_shards is None:
        required.add("num_shards")
    missing = sorted(required - set(dataframe.columns))
    if missing:
        raise ValueError("CSV is missing required columns: {}".format(", ".join(missing)))

    annotated = dataframe.drop(columns=MEXT_COLUMNS, errors="ignore").copy()
    rhos = []
    stable_outcomes = []
    for row in annotated.itertuples(index=False):
        row_values = row._asdict()
        if experiment_key in {"fig6", "fig7"}:
            parameters = reconstruct_point(
                experiment=experiment_key,
                alpha_inflow=row_values["alpha_inflow"],
                distribution=row_values["distribution"],
                epsilon_j0=row_values.get("epsilon_j0"),
                delta=row_values.get("delta"),
            )
        else:
            point_shards = num_shards
            if point_shards is None:
                point_shards = int(row_values.get("num_shards", 3))
            parameters = reconstruct_appendix_point(
                experiment=experiment_key,
                parameter=row_values[parameter_column],
                alpha=row_values[alpha_column],
                distribution=row_values["distribution"],
                max_delay=max_delay,
                num_shards=point_shards,
            )
        rho = spectral_radius(build_companion_matrix(**parameters))
        rhos.append(rho)
        stable_outcomes.append(rho < 1.0)

    annotated["mext_rho"] = np.asarray(rhos, dtype=float)
    annotated["mext_stable"] = np.asarray(stable_outcomes, dtype=bool)
    annotated["classification_match"] = (
        _boolean_series(annotated["converged"]) == annotated["mext_stable"]
    )
    return annotated


def annotate_csv(
    input_path: Union[str, Path],
    output_path: Union[str, Path],
    experiment: str,
    max_delay: Optional[int] = None,
    num_shards: Optional[int] = None,
) -> Dict[str, object]:
    source = Path(input_path)
    destination = Path(output_path)
    dataframe = pd.read_csv(source)
    annotated = annotate_dataframe(
        dataframe,
        experiment=experiment,
        max_delay=max_delay,
        num_shards=num_shards,
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination.with_name(destination.name + ".tmp")
    annotated.to_csv(temporary_path, index=False)
    temporary_path.replace(destination)

    match_count = int(annotated["classification_match"].sum())
    return {
        "input": str(source),
        "output": str(destination),
        "rows": len(annotated),
        "matches": match_count,
        "agreement": match_count / len(annotated) if len(annotated) else float("nan"),
    }


# The paper's figure numbers, mapped onto the internal sweep ids. The ids predate
# the paper's final numbering, and several of them collide with a different paper
# figure of the same number, so only the paper's spellings are accepted.
PAPER_NAMES = {
    "fig4a": "fig6",
    "fig4c": "fig7",
    "fig9-top": "fig10",
    "fig9-bottom": "fig11",
    "fig10": "fig12",
    "fig12": "fig13",
    "fig13": "fig14",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Append exact M_ext classifications to a sweep CSV."
    )
    parser.add_argument(
        "experiment",
        choices=list(PAPER_NAMES),
        help="the paper figure the CSV belongs to",
    )
    parser.add_argument("csv", nargs="+", type=Path)
    parser.add_argument(
        "--max-delay",
        type=int,
        help="delay metadata required by Figure 12; other figures use their fixed value",
    )
    parser.add_argument(
        "--num-shards",
        type=int,
        help="optional chain-count override, which Figure 13 otherwise reads from each row",
    )
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument(
        "--in-place",
        action="store_true",
        help="atomically replace each input CSV",
    )
    destination.add_argument(
        "--output-dir",
        type=Path,
        help="write annotated files with the same names under this directory",
    )
    return parser


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    experiment = PAPER_NAMES[args.experiment]
    for source in args.csv:
        destination = source if args.in_place else args.output_dir / source.name
        summary = annotate_csv(
            source,
            destination,
            experiment=experiment,
            max_delay=args.max_delay,
            num_shards=args.num_shards,
        )
        print(
            "{output}: {matches}/{rows} classifications agree ({agreement:.3%})".format(
                **summary
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
