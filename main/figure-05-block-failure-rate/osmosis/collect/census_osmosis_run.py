import csv, json, os, random, time, threading, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

H_LO, H_HI = 57_772_000, 67_958_290
THRESH = 3.0
PRIMARY = "https://rpc.osmosis.citizenweb3.com"
FALLBACK = "https://osmosis-rpc.noders.services"
RATE, WORKERS = 24.0, 14
D = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(D, "..", "data", "census_osmosis")
os.makedirs(OUT, exist_ok=True)

_lock, _next_ok = threading.Lock(), [0.0]
_fb_lock, _fb_next_ok = threading.Lock(), [0.0]

def _pace(fb=False):
    lk, arr, dt = (_fb_lock, _fb_next_ok, 0.25) if fb else (_lock, _next_ok, 1.0 / RATE)
    with lk:
        t = max(arr[0], time.time())
        arr[0] = t + dt
    d = t - time.time()
    if d > 0:
        time.sleep(d)

def get(path, tries=6):
    last = None
    for a in range(tries):
        fb = a >= 4
        _pace(fb)
        try:
            with urllib.request.urlopen((FALLBACK if fb else PRIMARY) + path, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            last = e
            time.sleep(3.0 if e.code == 429 else 0.8 * (a + 1))
        except Exception as e:
            last = e
            time.sleep(0.8 * (a + 1))
    raise RuntimeError(f"GET {path}: {last}")

def parse_ts(s):
    import datetime as dt
    frac = 0.0
    if "." in s:
        base, rest = s.split(".")
        frac = float("0." + rest.rstrip("Z"))
        s = base + "Z"
    t = dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    return t.timestamp() + frac

def stage1():
    path = os.path.join(OUT, "headers.csv")
    done_hi = H_LO - 1
    if os.path.exists(path):
        with open(path) as f:
            for line in f:
                pass
        try:
            done_hi = int(line.split(",")[0])
        except Exception:
            pass
    if done_hi >= H_HI:
        print("S1 already complete", flush=True)
        return
    print(f"S1: sweeping {done_hi+1}..{H_HI}", flush=True)
    write_lock = threading.Lock()
    f = open(path, "a", newline="")
    w = csv.writer(f)
    if done_hi == H_LO - 1:
        w.writerow(["height", "ts", "bytes", "ntxs", "proposer"])
    starts = list(range(done_hi + 1, H_HI + 1, 20))
    buf = {}
    next_flush = [done_hi + 1]
    def flush_ready():
        while next_flush[0] in buf:
            rows = buf.pop(next_flush[0])
            for r in rows:
                w.writerow(r)
            next_flush[0] += len(rows)
        f.flush()
    n_done = [0]
    def one(a):
        b = min(a + 19, H_HI)
        d = get(f"/blockchain?minHeight={a}&maxHeight={b}")["result"]["block_metas"]
        rows = []
        for m in sorted(d, key=lambda m: int(m["header"]["height"])):
            h = int(m["header"]["height"])
            rows.append([h, f"{parse_ts(m['header']['time']):.3f}", m["block_size"],
                         m["num_txs"], m["header"]["proposer_address"]])
        with write_lock:
            buf[a] = rows
            flush_ready()
            n_done[0] += 1
            if n_done[0] % 2000 == 0:
                print(f"[{time.strftime('%H:%M:%S')}] S1 {n_done[0]}/{len(starts)} calls "
                      f"(height ~{next_flush[0]:,})", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, starts))
    with write_lock:
        flush_ready()
    f.close()
    print("S1 done", flush=True)

def commit_compact(h):
    c = get(f"/commit?height={h}")["result"]["signed_header"]["commit"]
    flags = [s["block_id_flag"] for s in c["signatures"]]
    return {"h": h, "round": int(c["round"]), "n": len(flags),
            "absent": flags.count(1), "nil": flags.count(3)}

def fetch_commits(heights, out_name, label):
    path = os.path.join(OUT, out_name)
    done = set()
    if os.path.exists(path):
        for line in open(path):
            try:
                done.add(json.loads(line)["h"])
            except Exception:
                pass
    todo = [h for h in heights if h not in done]
    print(f"{label}: {len(todo)} commits to fetch ({len(done)} done)", flush=True)
    lk = threading.Lock()
    f = open(path, "a")
    n = [0]
    def one(h):
        try:
            r = commit_compact(h)
            with lk:
                f.write(json.dumps(r, separators=(",", ":")) + "\n")
                n[0] += 1
                if n[0] % 2000 == 0:
                    f.flush()
                    print(f"[{time.strftime('%H:%M:%S')}] {label} {n[0]}/{len(todo)}", flush=True)
        except Exception as e:
            print(f"{label} {h} FAILED: {e}", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    f.close()
    print(f"{label} done", flush=True)

def load_headers():
    hs, ts, bs = [], [], []
    with open(os.path.join(OUT, "headers.csv")) as f:
        rd = csv.reader(f)
        next(rd)
        for row in rd:
            hs.append(int(row[0])); ts.append(float(row[1])); bs.append(int(row[2]))
    return hs, ts, bs

def stage23():
    hs, ts, bs = load_headers()
    print(f"S2: {len(hs):,} headers loaded", flush=True)
    flagged = [hs[i] for i in range(len(hs) - 1) if ts[i + 1] - ts[i] >= THRESH]
    print(f"S2: {len(flagged):,} heights with interval >= {THRESH}s", flush=True)
    fetch_commits(flagged, "commits_flagged.jsonl", "S2")
    normal = [hs[i] for i in range(len(hs) - 1) if ts[i + 1] - ts[i] < THRESH]
    rng = random.Random(20260806)
    calib = rng.sample(normal, min(20000, len(normal)))
    fetch_commits(calib, "commits_calib.jsonl", "S3")

def stage4():
    events = []
    for line in open(os.path.join(OUT, "commits_flagged.jsonl")):
        r = json.loads(line)
        if r["round"] > 0:
            events.append(r["h"])
    hs, ts, bs = load_headers()
    import bisect
    bsorted = sorted(bs)
    p99 = bsorted[int(0.99 * len(bsorted))]
    big = [hs[i] for i in range(len(hs)) if bs[i] >= p99]
    systematic = hs[::100]
    targets = sorted(set([h - 1 for h in events] + big + systematic) & set(hs))
    print(f"S4: gas for {len(targets):,} heights "
          f"({len(events):,} events, {len(big):,} big-bytes>= {p99}, {len(systematic):,} systematic)", flush=True)
    path = os.path.join(OUT, "gas.csv")
    done = set()
    if os.path.exists(path):
        with open(path) as f:
            rd = csv.reader(f)
            next(rd, None)
            done = {int(r[0]) for r in rd}
    todo = [h for h in targets if h not in done]
    lk = threading.Lock()
    f = open(path, "a", newline="")
    w = csv.writer(f)
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
                if n[0] % 2000 == 0:
                    f.flush()
                    print(f"[{time.strftime('%H:%M:%S')}] S4 {n[0]}/{len(todo)}", flush=True)
        except Exception as e:
            print(f"S4 {h} FAILED: {e}", flush=True)
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(one, todo))
    f.close()
    print("S4 done", flush=True)

def pilot():
    import random
    hs, ts, bs = load_headers()
    rng = random.Random(20260806)
    sample = sorted(rng.sample(hs[:-1], 20000))
    fetch_commits(sample, "commits_pilot.jsonl", "PILOT")

if __name__ == "__main__":
    stage1()
    pilot()
    print("S1+PILOT COMPLETE", flush=True)
