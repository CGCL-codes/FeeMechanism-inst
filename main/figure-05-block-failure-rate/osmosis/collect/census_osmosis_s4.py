import csv, json, os, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
import numpy as np, pandas as pd

SCREEN = 50_000
H0 = 57_772_000
PRIMARY = "https://rpc.osmosis.citizenweb3.com"
FALLBACK = "https://osmosis-rpc.noders.services"
RATE, WORKERS = 24.0, 14
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "census_osmosis")
P = os.path.dirname(os.path.abspath(__file__))

_l, _n = threading.Lock(), [0.0]
_fl, _fn = threading.Lock(), [0.0]
def _pace(fb=False):
    lk, arr, dt = (_fl, _fn, 0.4) if fb else (_l, _n, 1.0/RATE)
    with lk:
        t = max(arr[0], time.time()); arr[0] = t + dt
    d = t - time.time()
    if d > 0: time.sleep(d)

def get(path, tries=6):
    last = None
    for a in range(tries):
        fb = a >= 4
        _pace(fb)
        try:
            with urllib.request.urlopen((FALLBACK if fb else PRIMARY)+path, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e; time.sleep(3.0 if e.code == 429 else 0.8*(a+1))
        except Exception as e:
            last = e; time.sleep(0.8*(a+1))
    raise RuntimeError(f"{path}: {last}")

if __name__ == "__main__":
    bs = []
    for tag in "abc":
        bs.append(pd.read_csv(os.path.join(D, f"headers_{tag}.csv"),
                              usecols=["bytes"], dtype=np.int64)["bytes"].to_numpy())
    bs = np.concatenate(bs)
    targets = [int(H0 + i) for i in np.flatnonzero(bs >= SCREEN)]
    print(f"S4: {len(targets):,} heights with bytes >= {SCREEN:,}", flush=True)

    known = {}
    with open(os.path.join(D, "gas_events.csv")) as f:
        rd = csv.reader(f); next(rd)
        for r in rd: known[int(r[0])] = r[1:]
    with open(os.path.join(P, "ibc_gas_share_osmosis.csv")) as f:
        for r in csv.DictReader(f):
            gw = int(r["in_gw"]) + int(r["out_gw"]) + int(r["rel_gw"]) + int(r["loc_gw"])
            gu = int(r["in_gu"]) + int(r["out_gu"]) + int(r["rel_gu"]) + int(r["loc_gu"])
            known.setdefault(int(r["height"]), (gw, gu, -1))

    path = os.path.join(D, "gas_hiload.csv")
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            rd = csv.reader(f); next(rd, None)
            done = {int(r[0]) for r in rd}
    f = open(path, "a", newline=""); w = csv.writer(f)
    if not done:
        w.writerow(["height", "gw", "gu", "ntx"])
    reused = 0
    for h in targets:
        if h in done: continue
        if h in known:
            g = known[h]
            w.writerow([h, g[0], g[1], g[2]]); done.add(h); reused += 1
    f.flush()
    print(f"S4: reused {reused:,} known gas rows", flush=True)
    todo = [h for h in targets if h not in done]
    print(f"S4: {len(todo):,} to fetch", flush=True)
    lk = threading.Lock(); n = [0]
    def one(h):
        try:
            r = get(f"/block_results?height={h}")["result"]
            txs = r.get("txs_results") or []
            with lk:
                w.writerow([h, sum(int(t["gas_wanted"]) for t in txs),
                            sum(int(t["gas_used"]) for t in txs), len(txs)])
                n[0] += 1
                if n[0] % 5000 == 0:
                    f.flush()
                    print(f"[{time.strftime('%H:%M:%S')}] S4 {n[0]:,}/{len(todo):,}", flush=True)
        except Exception as e:
            print(f"S4 {h} FAIL {e}", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    f.close()
    print("S4 COMPLETE", flush=True)
