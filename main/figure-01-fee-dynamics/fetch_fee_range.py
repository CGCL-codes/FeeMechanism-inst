import argparse
import datetime as dt
import json
import math
import os
import time
from typing import Dict, List, Sequence, Tuple

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


DEFAULT_ETH_RPC = "https://ethereum-rpc.publicnode.com"


def _build_session(timeout: int = 20) -> requests.Session:
    sess = requests.Session()
    retry = Retry(total=3, backoff_factor=0.3, status_forcelist=[429, 500, 502, 503, 504], allowed_methods=["POST"])
    adapter = HTTPAdapter(max_retries=retry)
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    sess.request_timeout = timeout
    return sess


def _rpc_call(session: requests.Session, url: str, method: str, params: Sequence) -> Dict:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": list(params)}
    resp = session.post(url, json=payload, timeout=getattr(session, "request_timeout", 20))
    resp.raise_for_status()
    body = resp.json()
    if "error" in body:
        raise RuntimeError(f"RPC error on {method}: {body['error']}")
    return body["result"]


def _rpc_batch_call(session: requests.Session, url: str, calls: Sequence[Tuple[int, str, Sequence]]) -> Dict[int, Dict]:
    payload = [
        {"jsonrpc": "2.0", "id": call_id, "method": method, "params": list(params)}
        for call_id, method, params in calls
    ]
    resp = session.post(url, json=payload, timeout=getattr(session, "request_timeout", 20))
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, list):
        raise RuntimeError(f"Batch RPC returned {type(body)} instead of list")
    out: Dict[int, Dict] = {}
    for item in body:
        if "error" in item:
            raise RuntimeError(f"Batch RPC error on id {item.get('id')}: {item['error']}")
        out[int(item["id"])] = item["result"]
    return out


def _get_block(session: requests.Session, rpc: str, number: int) -> Dict:
    block = _rpc_call(session, rpc, "eth_getBlockByNumber", [hex(number), False])
    if block is None:
        raise RuntimeError(f"Block {number} is unavailable from RPC {rpc}")
    return block


def _effective_gas_price_wei(tx: Dict, base_fee_wei: int) -> int:
    max_fee = tx.get("maxFeePerGas")
    max_priority = tx.get("maxPriorityFeePerGas")
    if max_fee and max_priority:
        return min(int(max_fee, 16), base_fee_wei + int(max_priority, 16))
    gas_price = tx.get("gasPrice")
    if gas_price:
        return int(gas_price, 16)
    if max_priority:
        return base_fee_wei + int(max_priority, 16)
    return base_fee_wei


def _market_gas_price_wei(tx: Dict, base_fee_wei: int) -> int:
    price = _effective_gas_price_wei(tx, base_fee_wei)
    return max(price, base_fee_wei) if base_fee_wei > 0 else price


def _latest_block(session: requests.Session, rpc: str) -> Tuple[int, int]:
    latest = _rpc_call(session, rpc, "eth_getBlockByNumber", ["latest", False])
    num = int(latest["number"], 16)
    ts = int(latest["timestamp"], 16)
    return num, ts


def _find_block_by_timestamp(session: requests.Session, rpc: str, target_ts: int, latest_num: int) -> int:
    low, high = 0, latest_num
    while low < high:
        mid = (low + high) // 2
        blk = _get_block(session, rpc, mid)
        ts = int(blk["timestamp"], 16)
        if ts < target_ts:
            low = mid + 1
        else:
            high = mid
    return low


def _find_block_lte_timestamp(session: requests.Session, rpc: str, target_ts: int, latest_num: int) -> int:
    low, high = 0, latest_num
    while low < high:
        mid = (low + high + 1) // 2
        blk = _get_block(session, rpc, mid)
        ts = int(blk["timestamp"], 16)
        if ts <= target_ts:
            low = mid
        else:
            high = mid - 1
    return low


def _fee_history_range(
    session: requests.Session, rpc: str, start_block: int, end_block: int, percentile: int, verbose: bool = False
) -> pd.DataFrame:
    rows: List[Dict] = []
    remaining = end_block - start_block + 1
    cursor = end_block
    chunk = 100
    while remaining > 0:
        take = min(chunk, remaining)
        try:
            res = _rpc_call(session, rpc, "eth_feeHistory", [hex(take), hex(cursor), [percentile]])
        except RuntimeError as exc:
            msg = str(exc).lower()
            if "out of bounds" in msg or "invalid block range" in msg or "block range" in msg:
                if chunk == 1:
                    raise
                chunk = max(1, chunk // 2)
                if verbose:
                    print(f"[feeHistory] provider rejected block range, reducing chunk to {chunk} and retrying...", flush=True)
                continue
            raise
        oldest = int(res["oldestBlock"], 16)
        base_fees = res["baseFeePerGas"][:-1]
        rewards = res["reward"]
        gas_used_ratios = res.get("gasUsedRatio", [])
        for i, bf_hex in enumerate(base_fees):
            bn = oldest + i
            base_fee = int(bf_hex, 16) / 1e9
            median_priority_fee = int(rewards[i][0], 16) / 1e9 if rewards[i] else 0.0
            gas_used_ratio = float(gas_used_ratios[i]) if i < len(gas_used_ratios) else math.nan
            rows.append(
                {
                    "block": bn,
                    "base_fee_gwei": base_fee,
                    "effective_gas_price_gwei": base_fee + median_priority_fee,
                    "gas_used_ratio": gas_used_ratio,
                }
            )
        remaining -= take
        cursor = oldest - 1
        if verbose:
            print(f"[feeHistory] collected up to block {cursor}, {remaining} remaining (chunk {chunk})...", flush=True)
    df = pd.DataFrame(rows)
    df.sort_values("block", inplace=True)

    ts_list: List[int] = []
    block_numbers = [int(bn) for bn in df["block"]]
    for start in range(0, len(block_numbers), chunk):
        block_chunk = block_numbers[start : start + chunk]
        calls = [(bn, "eth_getBlockByNumber", [hex(bn), False]) for bn in block_chunk]
        try:
            blocks = _rpc_batch_call(session, rpc, calls)
        except RuntimeError:
            blocks = {bn: _get_block(session, rpc, bn) for bn in block_chunk}
        for bn in block_chunk:
            blk = blocks[bn]
            ts_list.append(int(blk["timestamp"], 16))
        time.sleep(0.01)
    df["timestamp"] = pd.to_datetime(ts_list, unit="s", utc=True)
    return df[
        [
            "timestamp",
            "block",
            "base_fee_gwei",
            "effective_gas_price_gwei",
        ]
    ]


def _manual_block_scan(
    session: requests.Session, rpc: str, start_block: int, end_block: int, verbose: bool = False
) -> pd.DataFrame:
    rows: List[Dict] = []
    batch_size = 20
    total = end_block - start_block + 1
    for chunk_start in range(start_block, end_block + 1, batch_size):
        chunk_end = min(end_block, chunk_start + batch_size - 1)
        block_numbers = list(range(chunk_start, chunk_end + 1))
        calls = [(bn, "eth_getBlockByNumber", [hex(bn), True]) for bn in block_numbers]
        try:
            blocks = _rpc_batch_call(session, rpc, calls)
        except RuntimeError:
            blocks = {
                bn: _rpc_call(session, rpc, "eth_getBlockByNumber", [hex(bn), True])
                for bn in block_numbers
            }
        for bn in block_numbers:
            blk = blocks[bn]
            ts = int(blk["timestamp"], 16)
            base_fee = int(blk.get("baseFeePerGas", "0x0"), 16) / 1e9
            base_fee_wei = int(blk.get("baseFeePerGas", "0x0"), 16)
            effective_prices: List[float] = []
            for tx in blk.get("transactions", []):
                effective_prices.append(_market_gas_price_wei(tx, base_fee_wei) / 1e9)
            gas_price_med = float(pd.Series(effective_prices).median()) if effective_prices else base_fee
            rows.append(
                {
                    "timestamp": pd.to_datetime(ts, unit="s", utc=True),
                    "block": bn,
                    "base_fee_gwei": base_fee,
                    "effective_gas_price_gwei": gas_price_med,
                }
            )
        done = chunk_end - start_block + 1
        if verbose and (done == total or done % 500 < batch_size):
            print(f"[manual] scanned {done}/{total} blocks", flush=True)
        time.sleep(0.01)
    return pd.DataFrame(rows)


def canonical_fee_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    if "effective_gas_price_gwei" not in df.columns:
        if "median_effective_gas_price_gwei" in df.columns:
            df["effective_gas_price_gwei"] = df["median_effective_gas_price_gwei"]
        elif "gas_price_gwei" in df.columns:
            df["effective_gas_price_gwei"] = df["gas_price_gwei"]
        elif "tip_gwei" in df.columns:
            df["effective_gas_price_gwei"] = df["base_fee_gwei"] + df["tip_gwei"]
        else:
            raise ValueError("Missing effective gas price column")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    columns = ["timestamp"]
    if "block" in df.columns:
        columns.append("block")
    columns.extend(["base_fee_gwei", "effective_gas_price_gwei"])
    if "chain" in df.columns:
        columns.insert(0, "chain")
    out = df[columns].copy()
    sort_cols = ["timestamp"] + (["block"] if "block" in out.columns else [])
    out.sort_values(sort_cols, inplace=True)
    return out


def minute_bins(df: pd.DataFrame) -> pd.DataFrame:
    work = canonical_fee_frame(df)
    work["minute"] = work["timestamp"].dt.floor("min")
    grouped = work.groupby("minute", as_index=False)
    out = grouped[["base_fee_gwei", "effective_gas_price_gwei"]].mean()
    out["block_count"] = grouped.size()["size"]
    out["first_block"] = grouped["block"].min()["block"].astype(int)
    out["last_block"] = grouped["block"].max()["block"].astype(int)
    if "chain" in work.columns:
        out.insert(0, "chain", grouped["chain"].first()["chain"])
    out.rename(columns={"minute": "timestamp"}, inplace=True)
    return out


def fee_summary_metrics(df: pd.DataFrame, base_col: str = "base_fee_gwei", effective_col: str = "effective_gas_price_gwei") -> Dict:
    work = canonical_fee_frame(df)
    base = pd.to_numeric(work[base_col], errors="coerce")
    effective = pd.to_numeric(work[effective_col], errors="coerce")
    valid_log = (base > 0) & (effective > 0)
    if valid_log.sum() >= 2:
        log_base = base[valid_log].map(math.log)
        log_effective = effective[valid_log].map(math.log)
        if log_base.nunique() < 2 or log_effective.nunique() < 2:
            corr = None
        else:
            corr = float(log_base.corr(log_effective))
            if math.isnan(corr):
                corr = None
    else:
        corr = None

    share = base / effective.where(effective > 0)
    share_clean = share.dropna()
    return {
        "rows": int(len(work)),
        "valid_log_rows": int(valid_log.sum()),
        "pearson_log_base_fee_vs_log_median_effective_gas_price": corr,
        "base_fee_share_mean": float(share_clean.mean()) if not share_clean.empty else None,
        "base_fee_share_median": float(share_clean.median()) if not share_clean.empty else None,
        "base_fee_share_p10": float(share_clean.quantile(0.10)) if not share_clean.empty else None,
        "base_fee_share_p90": float(share_clean.quantile(0.90)) if not share_clean.empty else None,
    }


def write_fee_outputs(df: pd.DataFrame, csv_path: str, chain: str, window: Tuple[str, str], unit: str = "gwei") -> None:
    df = canonical_fee_frame(df)
    if "chain" not in df.columns:
        df.insert(0, "chain", chain)
    os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
    df.to_csv(csv_path, index=False)

    stem, ext = os.path.splitext(csv_path)
    minute_path = f"{stem}_1min{ext or '.csv'}"
    minute_df = minute_bins(df)
    minute_df.to_csv(minute_path, index=False)

    summary = {
        "chain": chain,
        "from_ts": window[0],
        "to_ts": window[1],
        "unit": unit,
        "block_level": fee_summary_metrics(df),
        "one_minute_level": fee_summary_metrics(minute_df),
    }
    metrics_path = f"{stem}_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)


def fetch_range_for_chain(
    session: requests.Session,
    rpc: str,
    start_ts: int,
    end_ts: int,
    percentile: int,
    label: str,
    verbose: bool = False,
    force_manual: bool = False,
) -> pd.DataFrame:
    latest_num, latest_ts = _latest_block(session, rpc)
    if verbose:
        print(f"[{label}] latest block {latest_num} @ {pd.to_datetime(latest_ts, unit='s', utc=True)}", flush=True)
    start_block = _find_block_by_timestamp(session, rpc, start_ts, latest_num)
    end_block = _find_block_lte_timestamp(session, rpc, end_ts, latest_num)
    if start_block > end_block:
        raise SystemExit(f"[{label}] No blocks in the given window.")
    if verbose:
        print(f"[{label}] block range {start_block} -> {end_block} (count {end_block - start_block + 1})", flush=True)
    if force_manual:
        if verbose:
            print(f"[{label}] force manual per-block scan with full transactions.", flush=True)
        return _manual_block_scan(session, rpc, start_block, end_block, verbose=verbose)
    try:
        df = _fee_history_range(session, rpc, start_block, end_block, percentile, verbose=verbose)
    except RuntimeError as exc:
        if verbose:
            print(f"[{label}] feeHistory failed ({exc}); falling back to manual per-block scan (slower).", flush=True)
        df = _manual_block_scan(session, rpc, start_block, end_block, verbose=verbose)
    return df


def _iso_to_epoch(ts: str) -> int:
    return int(dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch fee history for ETH and optional EVM chain by time range.")
    parser.add_argument("--from-ts", required=True, help="Start time ISO8601, e.g. 2024-12-26T12:00:00Z")
    parser.add_argument("--to-ts", required=True, help="End time ISO8601, e.g. 2024-12-26T14:00:00Z")
    parser.add_argument("--eth-rpc", default=os.environ.get("ETH_RPC_URL", DEFAULT_ETH_RPC), help="ETH RPC URL.")
    parser.add_argument("--chain", default="eth", help="Slug for the primary RPC output, default eth.")
    parser.add_argument("--output", help="Primary output CSV, default data/<chain>_fee_range.csv.")
    parser.add_argument("--evm-rpc", help="Optional EVM RPC URL (Moonbeam/Astar/Acala etc.).")
    parser.add_argument("--evm-chain", default="evm", help="Slug for EVM output file, default evm.")
    parser.add_argument("--evm-output", help="Optional EVM output CSV.")
    parser.add_argument("--tip-percentile", type=int, default=50, help="Tip percentile (default 50 for median).")
    parser.add_argument("--force-manual", action="store_true", help="Use full per-block transaction scan instead of eth_feeHistory.")
    parser.add_argument("--timeout", type=int, default=20, help="HTTP timeout seconds.")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging.")
    args = parser.parse_args()

    start_ts = _iso_to_epoch(args.from_ts)
    end_ts = _iso_to_epoch(args.to_ts)
    if end_ts <= start_ts:
        raise SystemExit("to-ts must be later than from-ts")

    session = _build_session(timeout=args.timeout)
    os.makedirs("data", exist_ok=True)

    if args.verbose:
        print(f"[{args.chain}] window {args.from_ts} -> {args.to_ts}, RPC {args.eth_rpc}")
    eth_df = fetch_range_for_chain(
        session,
        args.eth_rpc,
        start_ts,
        end_ts,
        args.tip_percentile,
        label=args.chain,
        verbose=args.verbose,
        force_manual=args.force_manual,
    )
    eth_path = args.output or f"data/{args.chain}_fee_range.csv"
    write_fee_outputs(eth_df, eth_path, chain=args.chain, window=(args.from_ts, args.to_ts), unit="gwei")
    if args.verbose:
        print(f"[{args.chain}] saved {len(eth_df)} rows to {eth_path}")

    if args.evm_rpc:
        slug = args.evm_chain.replace(" ", "_")
        if args.verbose:
            print(f"[{slug}] window {args.from_ts} -> {args.to_ts}, RPC {args.evm_rpc}")
        evm_df = fetch_range_for_chain(
            session,
            args.evm_rpc,
            start_ts,
            end_ts,
            args.tip_percentile,
            label=slug,
            verbose=args.verbose,
            force_manual=args.force_manual,
        )
        evm_path = args.evm_output or f"data/{slug}_fee_range.csv"
        write_fee_outputs(evm_df, evm_path, chain=slug, window=(args.from_ts, args.to_ts), unit="gwei")
        if args.verbose:
            print(f"[{slug}] saved {len(evm_df)} rows to {evm_path}")

    print("Done.")


if __name__ == "__main__":
    main()
