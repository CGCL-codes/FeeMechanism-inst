import csv, json, os, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
import numpy as np

THRESH = 2.5
H0 = 57_772_000
PRIMARY = "https://rpc.osmosis.citizenweb3.com"
FALLBACK = "https://osmosis-rpc.noders.services"
RATE, WORKERS = 24.0, 14
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "census_osmosis")

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
    print(f"{label}: {len(todo):,} commits to fetch ({len(done):,} done)", flush=True)
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
                if n[0] % 5000 == 0:
                    f.flush()
                    print(f"[{time.strftime('%H:%M:%S')}] {label} {n[0]:,}/{len(todo):,}", flush=True)
        except Exception as e:
            print(f"{label} {h} FAIL {e}", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    f.close(); print(f"{label} done", flush=True)

def fetch_gas(heights, out_name, label):
    path = os.path.join(D, out_name)
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            rd = csv.reader(f); next(rd, None)
            done = {int(r[0]) for r in rd}
    todo = [h for h in heights if h not in done]
    print(f"{label}: {len(todo):,} block_results to fetch ({len(done):,} done)", flush=True)
    lk = threading.Lock(); f = open(path, "a", newline=""); w = csv.writer(f)
    if not done:
        w.writerow(["height", "gw", "gu", "ntx"])
    n = [0]
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

if __name__ == "__main__":
    dt = np.load(os.path.join(D, "_dt.npy"))
    flagged = [int(H0 + i) for i in np.flatnonzero(dt >= THRESH)]
    print(f"S2: {len(flagged):,} heights with interval >= {THRESH}s", flush=True)
    fetch_commits(flagged, "commits_flagged.jsonl", "S2")
    events = []
    for line in open(os.path.join(D, "commits_flagged.jsonl")):
        r = json.loads(line)
        if r["round"] > 0:
            events.append(r["h"])
    events = sorted(set(events))
    print(f"S3: {len(events):,} round>0 events -> gas at h-1", flush=True)
    fetch_gas([h - 1 for h in events], "gas_events.csv", "S3")
    print("S2S3 COMPLETE", flush=True)
