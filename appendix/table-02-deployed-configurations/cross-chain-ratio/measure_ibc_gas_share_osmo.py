import base64, csv, json, os, random, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor

PRIMARY = "https://rpc.osmosis.citizenweb3.com"
FALLBACK = "https://osmosis-rpc.noders.services"
RATE, WORKERS = 24.0, 14
D = os.path.dirname(os.path.abspath(__file__))
# Same data ships twice: as osmosis_ibc_gas_share.csv here and as
# ibc_gas_share_osmosis.csv under ../../figure-05-block-failure-rate/osmosis/data/,
# where the curve assembler reads it as the low-load denominator.
OUT = os.path.join(D, "osmosis_ibc_gas_share.csv")

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

RECV = b"/ibc.core.channel.v1.MsgRecvPacket"
XFER = b"/ibc.applications.transfer.v1.MsgTransfer"
PLUMB = (b"/ibc.core.client.v1.MsgUpdateClient", b"/ibc.core.channel.v1.MsgAcknowledgement",
         b"/ibc.core.channel.v1.MsgTimeout")

def classify(raw):
    if RECV in raw: return "inbound"
    if XFER in raw: return "outbound"
    if any(p in raw for p in PLUMB): return "relayer"
    return "local"

def one(h, w, lk, stats):
    try:
        blk = get(f"/block?height={h}")["result"]["block"]["data"]["txs"] or []
        res = get(f"/block_results?height={h}")["result"].get("txs_results") or []
        sums = {}
        for i, txb in enumerate(blk):
            if i >= len(res): break
            cls = classify(base64.b64decode(txb))
            gu, gw_ = int(res[i]["gas_used"]), int(res[i]["gas_wanted"])
            a, b = sums.get(cls, (0, 0))
            sums[cls] = (a + gu, b + gw_)
        row = [h]
        for cls in ("inbound", "outbound", "relayer", "local"):
            gu, gw_ = sums.get(cls, (0, 0))
            row += [gu, gw_]
        with lk:
            w.writerow(row)
            stats[0] += 1
            if stats[0] % 1000 == 0:
                print(f"[{time.strftime('%H:%M:%S')}] {stats[0]:,} heights", flush=True)
    except Exception as e:
        print(f"{h} FAILED: {e}", flush=True)

def main():
    rng = random.Random(20260807)
    heights = sorted(rng.sample(range(57_772_000, 67_958_291), 20000))
    done = set()
    if os.path.exists(OUT):
        with open(OUT) as f:
            rd = csv.reader(f); next(rd, None)
            done = {int(r[0]) for r in rd}
    todo = [h for h in heights if h not in done]
    print(f"{len(todo):,} heights to fetch", flush=True)
    f = open(OUT, "a", newline="")
    w = csv.writer(f)
    if not done:
        w.writerow(["height","in_gu","in_gw","out_gu","out_gw","rel_gu","rel_gw","loc_gu","loc_gw"])
    lk = threading.Lock(); stats = [0]
    with ThreadPoolExecutor(WORKERS) as ex:
        list(ex.map(lambda h: one(h, w, lk, stats), todo))
    f.close(); print("IBC GAS SHARE DONE", flush=True)

if __name__ == "__main__":
    main()
