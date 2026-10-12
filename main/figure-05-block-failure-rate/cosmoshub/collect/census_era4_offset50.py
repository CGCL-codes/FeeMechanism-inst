import csv, importlib.util, os, threading, time, json

D = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(D, "..", "data", "census_era4")

spec = importlib.util.spec_from_file_location("c", os.path.join(D, "census_era4.py"))
m = importlib.util.module_from_spec(spec)
import sys; sys.modules["c"] = m
src = open(os.path.join(D, "census_era4.py")).read().replace('if __name__ == "__main__":', 'if False:')
exec(compile(src, "census_era4.py", "exec"), m.__dict__)
heights = []
with open(os.path.join(DATA, "headers.csv")) as f:
    rd = csv.reader(f); next(rd)
    for r in rd: heights.append(int(r[0]))
targets = heights[50::100]
done = set()
with open(os.path.join(DATA, "gas.csv")) as f:
    rd = csv.reader(f); next(rd, None)
    done = {int(r[0]) for r in rd}
todo = [h for h in targets if h not in done]
print(f"offset-50 systematic: {len(todo):,} to fetch", flush=True)
lk = threading.Lock()
f = open(os.path.join(DATA, "gas.csv"), "a", newline="")
w = csv.writer(f); n = [0]
from concurrent.futures import ThreadPoolExecutor
def one(h):
    try:
        r = m.get(f"/block_results?height={h}")["result"]
        txs = r.get("txs_results") or []
        with lk:
            w.writerow([h, sum(int(t["gas_wanted"]) for t in txs), sum(int(t["gas_used"]) for t in txs), len(txs)])
            n[0] += 1
            if n[0] % 5000 == 0:
                f.flush(); print(f"[{time.strftime('%H:%M:%S')}] {n[0]}/{len(todo)}", flush=True)
    except Exception as e:
        print(f"{h} FAILED: {e}", flush=True)
with ThreadPoolExecutor(14) as ex:
    list(ex.map(one, todo))
f.close(); print("OFFSET50 DONE", flush=True)
