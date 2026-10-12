#!/usr/bin/env python3
"""Enlarge the cross-chain gas-share sample inside each chain's census window.

The ratio cannot be censused: it needs every transaction's gas classified by IBC
message type, which is one /block plus one /block_results call per block, so a
full window would be millions of calls. What we can do is draw a larger uniform
sample. Heights already present in the target file are skipped, and a uniform
draw over the window unioned with the existing in-window heights is still a
uniform sample of that window.

Classification and output schema match the original samplers exactly, so the
enlarged file is a drop-in replacement.

Usage: expand_gas_share.py hub|osmo [target_in_window_heights]
"""
import base64
import csv
import os
import json
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
RATE, WORKERS = 22.0, 12

CHAINS = {
    "hub": {
        # ccvalidators throttles hard after the 2025 packet census, so the
        # archive is the primary here and ccvalidators only the fallback.
        "primary": "https://rpc.cosmoshub-4-archive.citizenweb3.com",
        "fallback": "https://rpc.cosmoshub-main.ccvalidators.com",
        "out": os.path.join(HERE, "cosmoshub_ibc_gas_share.csv"),
        "window": (23_763_459, 29_114_836),   # 2025 calendar year
        "target": 60_000,
        "seed": 20260817,
    },
    "osmo": {
        "primary": "https://rpc.osmosis.citizenweb3.com",
        "fallback": "https://osmosis-rpc.noders.services",
        "out": os.path.join(HERE, "osmosis_ibc_gas_share.csv"),
        "window": (59_405_170, 67_958_290),   # first indexed packet onward
        "target": 80_000,
        "seed": 20260818,
    },
}

RECV = b"/ibc.core.channel.v1.MsgRecvPacket"
XFER = b"/ibc.applications.transfer.v1.MsgTransfer"
PLUMB = (b"/ibc.core.client.v1.MsgUpdateClient",
         b"/ibc.core.channel.v1.MsgAcknowledgement",
         b"/ibc.core.channel.v1.MsgTimeout")

_lock, _next = threading.Lock(), [0.0]
_flock, _fnext = threading.Lock(), [0.0]


def _pace(fb=False):
    lk, arr, dt = (_flock, _fnext, 0.5) if fb else (_lock, _next, 1.0 / RATE)
    with lk:
        t = max(arr[0], time.time())
        arr[0] = t + dt
    d = t - time.time()
    if d > 0:
        time.sleep(d)


def make_get(primary, fallback):
    def get(path, tries=7):
        last = None
        for attempt in range(tries):
            fb = attempt >= 4
            _pace(fb)
            try:
                url = (fallback if fb else primary) + path
                with urllib.request.urlopen(url, timeout=35) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                last = e
                time.sleep(20.0 if e.code == 429 else 0.9 * (attempt + 1))
            except Exception as e:
                last = e
                time.sleep(0.9 * (attempt + 1))
        raise RuntimeError(f"{path}: {last}")
    return get


def classify(raw):
    if RECV in raw:
        return "inbound"
    if XFER in raw:
        return "outbound"
    if any(p in raw for p in PLUMB):
        return "relayer"
    return "local"


def main():
    chain = sys.argv[1]
    cfg = CHAINS[chain]
    if len(sys.argv) > 2:
        cfg["target"] = int(sys.argv[2])
    get = make_get(cfg["primary"], cfg["fallback"])
    lo, hi = cfg["window"]

    done = set()
    with open(cfg["out"]) as f:
        rd = csv.reader(f)
        next(rd, None)
        done = {int(r[0]) for r in rd}
    in_window = {h for h in done if lo <= h <= hi}
    need = cfg["target"] - len(in_window)
    print(f"{chain}: {len(done):,} rows on file, {len(in_window):,} inside the "
          f"window, target {cfg['target']:,}, need {max(need, 0):,}", flush=True)
    if need <= 0:
        print("target already met", flush=True)
        return

    rng = random.Random(cfg["seed"])
    pool = rng.sample(range(lo, hi + 1), min(need * 2, hi - lo))
    todo = [h for h in pool if h not in done][:need]
    print(f"fetching {len(todo):,} new heights", flush=True)

    out = open(cfg["out"], "a", newline="")
    writer = csv.writer(out)
    lk = threading.Lock()
    stats = [0, 0]

    def one(h):
        try:
            blk = get(f"/block?height={h}")["result"]["block"]["data"]["txs"] or []
            res = get(f"/block_results?height={h}")["result"].get("txs_results") or []
            sums = {}
            for i, txb in enumerate(blk):
                if i >= len(res):
                    break
                cls = classify(base64.b64decode(txb))
                gu, gw = int(res[i]["gas_used"]), int(res[i]["gas_wanted"])
                a, b = sums.get(cls, (0, 0))
                sums[cls] = (a + gu, b + gw)
            row = [h]
            for cls in ("inbound", "outbound", "relayer", "local"):
                gu, gw = sums.get(cls, (0, 0))
                row += [gu, gw]
            with lk:
                writer.writerow(row)
                stats[0] += 1
                if stats[0] % 2000 == 0:
                    out.flush()
                    print(f"[{time.strftime('%H:%M:%S')}] {chain} "
                          f"{stats[0]:,}/{len(todo):,} ({stats[1]} failed)",
                          flush=True)
        except Exception as e:
            with lk:
                stats[1] += 1
                if stats[1] % 50 == 1:
                    print(f"{chain} {h} FAILED: {str(e)[:70]}", flush=True)

    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    out.close()
    print(f"{chain} EXPANSION DONE: {stats[0]:,} added, {stats[1]} failed",
          flush=True)


if __name__ == "__main__":
    main()
