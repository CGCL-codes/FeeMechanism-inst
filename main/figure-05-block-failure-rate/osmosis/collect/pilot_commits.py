import json, os, random, threading, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
PRIMARY="https://rpc.osmosis.citizenweb3.com"; FALLBACK="https://osmosis-rpc.noders.services"
RATE, WORKERS = 24.0, 12
D=os.path.dirname(os.path.abspath(__file__))
OUT=os.path.join(D,"..","data","census_osmosis","commits_pilot.jsonl")
_l,_n=threading.Lock(),[0.0]; _fl,_fn=threading.Lock(),[0.0]
def _pace(fb=False):
    lk,arr,dt=(_fl,_fn,0.4) if fb else (_l,_n,1.0/RATE)
    with lk:
        t=max(arr[0],time.time()); arr[0]=t+dt
    d=t-time.time()
    if d>0: time.sleep(d)
def get(p,tries=6):
    last=None
    for a in range(tries):
        fb=a>=4; _pace(fb)
        try:
            with urllib.request.urlopen((FALLBACK if fb else PRIMARY)+p,timeout=30) as r: return json.load(r)
        except urllib.error.HTTPError as e:
            last=e; time.sleep(3.0 if e.code==429 else 0.8*(a+1))
        except Exception as e:
            last=e; time.sleep(0.8*(a+1))
    raise RuntimeError(f"{p}: {last}")
rng=random.Random(20260806)
sample=sorted(rng.sample(range(57_772_001,67_958_290),20000))
done=set()
if os.path.exists(OUT):
    for l in open(OUT):
        try: done.add(json.loads(l)["h"])
        except Exception: pass
todo=[h for h in sample if h not in done]
print(f"{len(todo)} to fetch",flush=True)
f=open(OUT,"a"); lk=threading.Lock(); n=[0]
def one(h):
    try:
        c=get(f"/commit?height={h}")["result"]["signed_header"]["commit"]
        flags=[s["block_id_flag"] for s in c["signatures"]]
        with lk:
            f.write(json.dumps({"h":h,"round":int(c["round"]),"n":len(flags),"absent":flags.count(1),"nil":flags.count(3)},separators=(",",":"))+"\n")
            n[0]+=1
            if n[0]%2000==0: f.flush(); print(f"{n[0]}/{len(todo)}",flush=True)
    except Exception as e:
        print(f"{h} FAIL {e}",flush=True)
with ThreadPoolExecutor(WORKERS) as ex:
    list(ex.map(one,todo))
f.close(); print("PILOT DONE",flush=True)
