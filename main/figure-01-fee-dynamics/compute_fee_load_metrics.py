import json
import math
import os
import time
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

import pandas as pd

from fetch_fee_range import _build_session, _rpc_batch_call, canonical_fee_frame, minute_bins


FEE_DIR = Path(__file__).resolve().parent
DATA_DIR = FEE_DIR / "data"

CHAINS = {
    "moonbeam": {
        "date": "2025-03-21",
        "out_dir": DATA_DIR / "moonbeam_2025-03-21",
        "fee_csv": DATA_DIR / "moonbeam_2025-03-21" / "moonbeam_fee_range_2025-03-21.csv",
        "rpc": "https://rpc.api.moonbeam.network",
    },
    "eth": {
        "date": "2025-12-23",
        "out_dir": DATA_DIR / "eth_2025-12-23",
        "fee_csv": DATA_DIR / "eth_2025-12-23" / "eth_fee_range_2025-12-23.csv",
        "rpc": os.environ.get("ETH_RPC_URL", "https://ethereum-rpc.publicnode.com"),
    },
}


def _fetch_load_rows(chain: str, fee_df: pd.DataFrame, rpc: str, batch_size: int = 100) -> pd.DataFrame:
    session = _build_session(timeout=45)
    blocks = [int(block) for block in fee_df["block"]]
    rows: List[Dict] = []
    total = len(blocks)

    for start in range(0, total, batch_size):
        block_chunk = blocks[start : start + batch_size]
        calls = [(block, "eth_getBlockByNumber", [hex(block), False]) for block in block_chunk]
        batch = _rpc_batch_call(session, rpc, calls)
        for block in block_chunk:
            blk = batch[block]
            gas_used = int(blk.get("gasUsed", "0x0"), 16)
            gas_limit = int(blk.get("gasLimit", "0x0"), 16)
            rows.append(
                {
                    "chain": chain,
                    "timestamp": pd.to_datetime(int(blk["timestamp"], 16), unit="s", utc=True),
                    "block": block,
                    "gas_used": gas_used,
                    "gas_limit": gas_limit,
                    "load": gas_used / gas_limit if gas_limit > 0 else math.nan,
                    "tx_count": len(blk.get("transactions") or []),
                }
            )
        done = min(start + batch_size, total)
        if done == total or done % 1000 == 0:
            print(f"[{chain}] fetched load {done}/{total} blocks", flush=True)
        time.sleep(0.02)

    return pd.DataFrame(rows).sort_values(["timestamp", "block"])


def _metric_pair(df: pd.DataFrame) -> Dict:
    base = pd.to_numeric(df["base_fee_gwei"], errors="coerce")
    effective = pd.to_numeric(df["effective_gas_price_gwei"], errors="coerce")
    valid = (base > 0) & (effective > 0)
    if valid.sum() >= 2 and base[valid].nunique() >= 2 and effective[valid].nunique() >= 2:
        corr = float(base[valid].map(math.log).corr(effective[valid].map(math.log)))
        if math.isnan(corr):
            corr = None
    else:
        corr = None

    share = (base / effective.where(effective > 0)).dropna()
    return {
        "rows": int(len(df)),
        "valid_log_rows": int(valid.sum()),
        "pearson_log_base_fee_vs_log_median_effective_gas_price": corr,
        "base_fee_share_median": float(share.median()) if not share.empty else None,
        "base_fee_share_mean": float(share.mean()) if not share.empty else None,
    }


def _merge_fee_load(chain: str, fee_df: pd.DataFrame, load_df: pd.DataFrame) -> pd.DataFrame:
    fee = canonical_fee_frame(fee_df)
    if "chain" not in fee.columns:
        fee.insert(0, "chain", chain)
    merged = fee.merge(
        load_df[["block", "gas_used", "gas_limit", "load", "tx_count"]],
        on="block",
        how="left",
        validate="one_to_one",
    )
    return merged.sort_values(["timestamp", "block"])


def _write_chain_outputs(chain: str, cfg: Dict) -> Dict:
    date = cfg["date"]
    out_dir = cfg["out_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    fee_df = pd.read_csv(cfg["fee_csv"], parse_dates=["timestamp"])
    fee_df = canonical_fee_frame(fee_df)
    if "chain" not in fee_df.columns:
        fee_df.insert(0, "chain", chain)

    load_path = out_dir / f"{chain}_load_{date}.csv"
    if load_path.exists():
        load_df = pd.read_csv(load_path, parse_dates=["timestamp"])
    else:
        load_df = _fetch_load_rows(chain, fee_df, cfg["rpc"])
        load_df.to_csv(load_path, index=False)
        print(f"[{chain}] saved load to {load_path}", flush=True)

    merged = _merge_fee_load(chain, fee_df, load_df)
    fee_load_path = out_dir / f"{chain}_fee_load_{date}.csv"
    merged.to_csv(fee_load_path, index=False)

    minute_df = minute_bins(merged)
    minute_path = out_dir / f"{chain}_fee_load_{date}_1min.csv"
    minute_df.to_csv(minute_path, index=False)

    threshold = float(merged["load"].quantile(0.90))
    top = merged[merged["load"] >= threshold].copy()
    top_path = out_dir / f"{chain}_fee_load_top10pct_load_{date}.csv"
    top.to_csv(top_path, index=False)

    summary = {
        "chain": chain,
        "date": date,
        "load_top10_threshold": threshold,
        "outputs": {
            "load_csv": str(load_path),
            "fee_load_csv": str(fee_load_path),
            "fee_load_1min_csv": str(minute_path),
            "top10_load_block_csv": str(top_path),
        },
        "overall_block_level": _metric_pair(merged),
        "top10_load_block_level": _metric_pair(top),
    }
    metrics_path = out_dir / f"{chain}_fee_load_metrics_{date}.json"
    metrics_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[{chain}] saved metrics to {metrics_path}", flush=True)
    return summary


def main() -> None:
    summaries = {chain: _write_chain_outputs(chain, cfg) for chain, cfg in CHAINS.items()}
    combined_path = DATA_DIR / "fee_load_metrics_moonbeam_eth.json"
    combined_path.write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(f"Saved combined metrics to {combined_path}", flush=True)


if __name__ == "__main__":
    main()
