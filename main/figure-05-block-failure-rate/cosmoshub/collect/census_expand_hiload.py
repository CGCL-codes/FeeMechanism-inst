import csv, json, os, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

MG = 75_000_000
SEED_FRAC, STOP_FRAC, EDGE = 0.5, 0.35, 30
H_LO, H_HI = 22_848_761, 32_363_858
PRIMARY = "https://rpc.cosmoshub-4-archive.citizenweb3.com"
FALLBACK = "https://rpc.cosmoshub-main.ccvalidators.com"
RATE, WORKERS = 26.0, 14
D = os.path.dirname(os.path.abspath(__file__))
GAS = os.path.join(D, "..", "data", "census_era4", "gas.csv")

_lock, _next = threading.Lock(), [0.0]
_fbl, _fbn = threading.Lock(), [0.0]
def _pace(fb=False):
    lk, arr, dt = (_fbl, _fbn, 1.2) if fb else (_lock, _next, 1.0/RATE)
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

gas = {}
with open(GAS) as f:
    rd = csv.reader(f); next(rd)
    for r in rd: gas[int(r[0])] = (int(r[1]), int(r[2]), int(r[3]) if len(r) > 3 else 0)

out = open(GAS, "a", newline="")
w = csv.writer(out)
wl = threading.Lock()
fetched = [0]
def fetch(h):
    r = get(f"/block_results?height={h}")["result"]
    txs = r.get("txs_results") or []
    gw = sum(int(t["gas_wanted"]) for t in txs); gu = sum(int(t["gas_used"]) for t in txs)
    with wl:
        w.writerow([h, gw, gu, len(txs)])
        gas[h] = (gw, gu, len(txs))
        fetched[0] += 1
        if fetched[0] % 1000 == 0:
            out.flush()
            print(f"[{time.strftime('%H:%M:%S')}] fetched {fetched[0]:,} (known {len(gas):,})", flush=True)
    return gw

seeds = sorted(h for h, (gw, _, _) in gas.items() if gw >= SEED_FRAC*MG)
print(f"{len(seeds)} seeds >= {SEED_FRAC:.0%} packing", flush=True)

intervals = []
for s in seeds:
    if intervals and s - intervals[-1][1] <= 2*EDGE: intervals[-1][1] = s
    else: intervals.append([s, s])
print(f"{len(intervals)} initial regions", flush=True)

def expand(iv):
    lo, hi = iv
    run = 0; h = lo - 1
    while run < EDGE and h >= H_LO:
        gw = gas[h][0] if h in gas else fetch(h)
        run = run + 1 if gw < STOP_FRAC*MG else 0
        h -= 1
    run = 0; h = hi + 1
    while run < EDGE and h <= H_HI:
        gw = gas[h][0] if h in gas else fetch(h)
        run = run + 1 if gw < STOP_FRAC*MG else 0
        h += 1

with ThreadPoolExecutor(WORKERS) as ex:
    list(ex.map(expand, intervals))
out.flush(); out.close()
print(f"EXPANSION DONE fetched={fetched[0]:,} total_known={len(gas):,}", flush=True)
