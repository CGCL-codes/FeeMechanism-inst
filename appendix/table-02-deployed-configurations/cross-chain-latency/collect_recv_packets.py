#!/usr/bin/env python3
"""Inbound IBC packet collector, all channels.

N_HEIGHTS caps a run at a seeded draw of heights, so this reproduces a sample
of the shipped censuses rather than the censuses themselves. It writes
recv_delays_<chain>.csv in the schema of the shipped .csv.gz files.

Random heights across the census era, /block_results per height, every
recv_packet event's timeout timestamp. Delay is recovered later by clustering
the margins (timeout - recv time) below the standard windows, exactly as in
the corrected episode analysis. Receive times come from the on-disk headers,
so the only network cost is one block_results call per sampled height.

Usage: collect_recv_packets.py hub|osmo
"""
import csv
import json
import os
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np

D = os.path.dirname(os.path.abspath(__file__))
P = os.path.dirname(D)
N_HEIGHTS = 20_000
RATE, WORKERS = 20.0, 12
SEED = 811

CHAINS = {
    "hub": {
        "primary": "https://rpc.cosmoshub-4-archive.citizenweb3.com",
        "fallback": "https://rpc.cosmoshub-main.ccvalidators.com",
        "headers": os.path.join(P, "cosmoshub-round-history-2026-08-05",
                                "census_era4", "headers.csv"),
    },
    "osmo": {
        "primary": "https://rpc.osmosis.citizenweb3.com",
        "fallback": "https://osmosis-rpc.noders.services",
        "heights_npy": os.path.join(P, "osmosis-round-census-2026-08-06",
                                    "census_osmosis", "_heights.npy"),
        "ts_npy": os.path.join(P, "osmosis-round-census-2026-08-06",
                               "census_osmosis", "_ts.npy"),
    },
}

_lock, _next = threading.Lock(), [0.0]
_flock, _fnext = threading.Lock(), [0.0]


def _pace(fb=False):
    lk, arr, dt = (_flock, _fnext, 1.2) if fb else (_lock, _next, 1.0 / RATE)
    with lk:
        t = max(arr[0], time.time())
        arr[0] = t + dt
    d = t - time.time()
    if d > 0:
        time.sleep(d)


def make_get(primary, fallback):
    def get(path, tries=6):
        last = None
        for attempt in range(tries):
            fb = attempt >= 4
            _pace(fb)
            try:
                url = (fallback if fb else primary) + path
                with urllib.request.urlopen(url, timeout=40) as r:
                    return json.load(r)
            except urllib.error.HTTPError as e:
                last = e
                time.sleep(3.0 if e.code == 429 else 0.8 * (attempt + 1))
            except Exception as e:
                last = e
                time.sleep(0.8 * (attempt + 1))
        raise RuntimeError(f"{path}: {last}")
    return get


def sample_heights(chain):
    """(height, block_time) pairs for the random sample, from disk caches."""
    rng = random.Random(SEED)
    if chain == "hub":
        heights, times = [], []
        with open(CHAINS["hub"]["headers"]) as f:
            rd = csv.reader(f)
            next(rd)
            for row in rd:
                if int(row[3]) > 0:          # ntxs > 0
                    heights.append(int(row[0]))
                    times.append(float(row[1]))
        idx = rng.sample(range(len(heights)), N_HEIGHTS)
        return [(heights[i], times[i]) for i in idx]
    h = np.load(CHAINS["osmo"]["heights_npy"])
    t = np.load(CHAINS["osmo"]["ts_npy"])
    idx = rng.sample(range(len(h)), N_HEIGHTS)
    return [(int(h[i]), float(t[i])) for i in idx]


def attr_map(event):
    out = {}
    for a in event.get("attributes", []):
        k, v = a.get("key", ""), a.get("value", "")
        try:                                  # older nodes b64-encode both
            import base64
            k2 = base64.b64decode(k).decode()
            v2 = base64.b64decode(v).decode()
            if k2.replace("_", "").isalnum():
                k, v = k2, v2
        except Exception:
            pass
        out[k] = v
    return out


def main():
    chain = sys.argv[1]
    cfg = CHAINS[chain]
    get = make_get(cfg["primary"], cfg["fallback"])
    sample = sample_heights(chain)
    out_path = os.path.join(D, f"recv_delays_{chain}.csv")
    done_heights = set()
    if os.path.exists(out_path):
        with open(out_path) as f:
            done_heights = {int(r["height"]) for r in csv.DictReader(f)}
    mode = "a" if done_heights else "w"
    out = open(out_path, mode, newline="")
    w = csv.writer(out)
    if mode == "w":
        w.writerow(["height", "block_time", "seq", "src_channel",
                    "timeout_minus_recv_s"])
    lock = threading.Lock()
    counts = [0, 0]

    def work(pair):
        height, btime = pair
        if height in done_heights:
            return
        res = get(f"/block_results?height={height}")
        rows = []
        for tx in (res.get("result", {}).get("txs_results") or []):
            if tx.get("code", 0) != 0:
                continue
            for ev in tx.get("events", []):
                if ev.get("type") != "recv_packet":
                    continue
                a = attr_map(ev)
                ts = a.get("packet_timeout_timestamp", "0")
                ch = a.get("packet_dst_channel", "")
                seq = a.get("packet_sequence", "")
                if not ts or ts == "0":
                    continue
                margin = int(ts) / 1e9 - btime
                rows.append([height, f"{btime:.3f}", seq, ch,
                             f"{margin:.2f}"])
        with lock:
            counts[0] += 1
            counts[1] += len(rows)
            for r in rows:
                w.writerow(r)
            if counts[0] % 500 == 0:
                out.flush()
                print(f"{chain}: {counts[0]}/{len(sample)} heights, "
                      f"{counts[1]} packets", flush=True)

    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        list(ex.map(work, sample))
    out.close()
    print(f"{chain} DONE: {counts[0]} heights, {counts[1]} packets", flush=True)


if __name__ == "__main__":
    main()
