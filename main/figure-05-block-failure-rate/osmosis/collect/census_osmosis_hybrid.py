import csv, json, os, random, threading, time, urllib.request, urllib.error
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

def fetch_commits(heights, out_name, label):
    path = os.path.join(D, out_name)
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try: done.add(json.loads(line)["h"])
            except Exception: pass
    todo = [h for h in heights if h not in done]
    print(f"{label}: {len(todo):,} commits to fetch ({len(done):,} already on file)", flush=True)
    lk = threading.Lock(); f = open(path, "a"); n = [0]
    def one(h):
        try:
            c = get(f"/commit?height={h}")["result"]["signed_header"]["commit"]
            flags = [s["block_id_flag"] for s in c["signatures"]]
            with lk:
                f.write(json.dumps({"h": h, "round": int(c["round"]), "n": len(flags),
                                    "absent": flags.count(1), "nil": flags.count(3)},
                                   separators=(",", ":")) + "\n")
                n[0] += 1
                if n[0] % 2000 == 0:
                    f.flush()
                    print(f"[{time.strftime('%H:%M:%S')}] {label} {n[0]:,}/{len(todo):,}", flush=True)
        except Exception as e:
            print(f"{label} {h} FAIL {e}", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    f.close(); print(f"{label} done", flush=True)

def fetch_gas(heights, out_name, label, known=None):
    path = os.path.join(D, out_name)
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            rd = csv.reader(f); next(rd, None)
            done = {int(r[0]) for r in rd}
    f = open(path, "a", newline=""); w = csv.writer(f)
    if not done:
        w.writerow(["height", "gw", "gu", "ntx"])
    reused = 0
    if known:
        for h in heights:
            if h in done or h not in known: continue
            g = known[h]
            w.writerow([h, g[0], g[1], g[2]]); done.add(h); reused += 1
        f.flush()
    todo = [h for h in heights if h not in done]
    print(f"{label}: {len(todo):,} block_results to fetch "
          f"({len(done)-reused:,} on file, {reused:,} reused)", flush=True)
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
                    print(f"[{time.strftime('%H:%M:%S')}] {label} {n[0]:,}/{len(todo):,}", flush=True)
        except Exception as e:
            print(f"{label} {h} FAIL {e}", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    f.close(); print(f"{label} done", flush=True)

def load_gas_csv(path):
    out = {}
    if os.path.exists(path):
        with open(path) as f:
            rd = csv.reader(f); next(rd, None)
            for r in rd: out[int(r[0])] = (int(r[1]), int(r[2]), int(r[3]))
    return out

if __name__ == "__main__":
    ev = np.load(os.path.join(D, "_event_heights.npy"))
    bs = []
    for tag in "abc":
        bs.append(pd.read_csv(os.path.join(D, f"headers_{tag}.csv"),
                              usecols=["bytes"], dtype=np.int64)["bytes"].to_numpy())
    bs = np.concatenate(bs)

    e_hi = [int(h) for h in ev[bs[ev - 1 - H0] >= SCREEN]]
    print(f"A: {len(e_hi):,} events with bytes(h-1) >= {SCREEN:,}", flush=True)
    fetch_commits(e_hi, "commits_flagged.jsonl", "A")

    hiload = [int(H0 + i) for i in np.flatnonzero(bs >= SCREEN)]
    known = {}
    with open(os.path.join(P, "ibc_gas_share_osmosis.csv")) as f:
        for r in csv.DictReader(f):
            gw = int(r["in_gw"]) + int(r["out_gw"]) + int(r["rel_gw"]) + int(r["loc_gw"])
            gu = int(r["in_gu"]) + int(r["out_gu"]) + int(r["rel_gu"]) + int(r["loc_gu"])
            known[int(r["height"])] = (gw, gu, -1)
    print(f"B: {len(hiload):,} heights with bytes >= {SCREEN:,}", flush=True)
    fetch_gas(hiload, "gas_hiload.csv", "B", known=known)

    rng = random.Random(20260808)
    sample = sorted(rng.sample([int(h) for h in ev], 50_000))
    with open(os.path.join(D, "_event_sample.json"), "w") as f:
        json.dump(sample, f)
    known.update(load_gas_csv(os.path.join(D, "gas_hiload.csv")))
    fetch_gas([h - 1 for h in sample], "gas_events_sample.csv", "C", known=known)
    print("HYBRID COMPLETE", flush=True)
