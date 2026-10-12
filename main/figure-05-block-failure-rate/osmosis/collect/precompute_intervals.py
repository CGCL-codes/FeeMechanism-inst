import numpy as np, pandas as pd, os

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "census_osmosis")
parts = []
for tag in ("a", "b", "c"):
    df = pd.read_csv(os.path.join(D, f"headers_{tag}.csv"),
                     usecols=["height", "ts"], dtype={"height": np.int64, "ts": np.float64})
    parts.append(df)
    print(tag, len(df), df["height"].iloc[0], df["height"].iloc[-1], flush=True)
df = pd.concat(parts, ignore_index=True)
h = df["height"].to_numpy()
ts = df["ts"].to_numpy()
assert (np.diff(h) == 1).all(), "headers not contiguous"
dt = np.diff(ts)
np.save(os.path.join(D, "_heights.npy"), h)
np.save(os.path.join(D, "_ts.npy"), ts)
np.save(os.path.join(D, "_dt.npy"), dt)
print(f"{len(h):,} heights {h[0]}..{h[-1]}, {len(dt):,} intervals")
q = np.quantile(dt, [0.5, 0.9, 0.99, 0.999, 0.9999])
print("dt quantiles p50/p90/p99/p99.9/p99.99:", [f"{v:.3f}" for v in q])
print("mean", f"{dt.mean():.4f}", "max", f"{dt.max():.2f}", "min", f"{dt.min():.3f}")
for t in (2.0, 2.25, 2.5, 2.75, 3.0, 3.25, 3.5, 4.0, 5.0, 6.0, 8.0):
    print(f"dt>={t:>5}: {(dt>=t).sum():,}")
