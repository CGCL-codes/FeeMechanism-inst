"""Table 2's cross-chain delay, measured from every inbound IBC packet.

Appendix C.2. An IBC packet carries a channel identifier and a sequence number,
so a receive on the destination chain matches exactly one send on the source
chain. The destination-side record does not carry the send time, but it carries
the packet's timeout, and a relayer sets that timeout from one of three standard
windows. The margin between the timeout and the receive time therefore recovers
the elapsed delay, and a packet whose margin falls outside every window uses a
non-standard timeout and is dropped.

The delay in destination-chain blocks is the elapsed time divided by the chain's
realized mean block interval over its own census window. Table 2 carries the
mean, rounded, as `d_max`.
"""
import argparse
import csv
import gzip
from collections import defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent

# The three standard relayer timeout windows, in seconds.
WINDOWS = (300.0, 600.0, 1200.0)

CHAINS = {
    "Cosmos Hub": {
        "file": "cosmoshub_recv_packets_2025.csv.gz",
        "interval": 5.8931,
        "window": "January 1 to December 31, 2025",
    },
    "Osmosis": {
        "file": "osmosis_recv_packets_2026.csv.gz",
        "interval": 1.1478,
        "window": "April 15 to August 6, 2026",
    },
}


def delay_of(margin):
    """Elapsed delay in seconds, or None when the packet uses no standard window."""
    for window in WINDOWS:
        if 0 < margin <= window:
            return window - margin
    return None


def load(path):
    by_channel = defaultdict(list)
    rows = 0
    with gzip.open(path, "rt") as handle:
        for record in csv.DictReader(handle):
            rows += 1
            delay = delay_of(float(record["timeout_minus_recv_s"]))
            if delay is not None:
                by_channel[record["src_channel"]].append(delay)
    return by_channel, rows


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=HERE)
    parser.add_argument("--bootstrap", type=int, default=500)
    args = parser.parse_args(argv)

    for name, config in CHAINS.items():
        path = args.data_dir / config["file"]
        if not path.exists():
            print(f"{name}: {config['file']} missing, skipped\n")
            continue
        by_channel, rows = load(path)
        interval = config["interval"]
        pooled = np.concatenate([np.array(v) for v in by_channel.values()])
        generator = np.random.default_rng(11)
        boot = np.array([generator.choice(pooled, len(pooled)).mean()
                         for _ in range(args.bootstrap)]) / interval

        print(f"=== {name} ({config['window']}) ===")
        print(f"  rows {rows:,}  usable {len(pooled):,}  channels {len(by_channel)}")
        print(f"  mean {pooled.mean() / interval:.2f} blocks  "
              f"CI [{np.percentile(boot, 2.5):.2f}, {np.percentile(boot, 97.5):.2f}]"
              f"   d_max = {round(pooled.mean() / interval)}")
        print(f"  mean seconds {pooled.mean():.1f}  block interval {interval:.4f} s")

        ranked = sorted(by_channel.items(), key=lambda item: -len(item[1]))
        print("  channel        packets   share   mean(blk)")
        for channel, values in ranked[:5]:
            values = np.array(values)
            print(f"    {channel:<12} {len(values):8,}  "
                  f"{100 * len(values) / len(pooled):5.1f}%   {values.mean() / interval:7.2f}")
        rest = ranked[5:]
        if rest:
            tail = np.concatenate([np.array(v) for _, v in rest])
            print(f"    {f'({len(rest)} others)':<12} {len(tail):8,}  "
                  f"{100 * len(tail) / len(pooled):5.1f}%   {tail.mean() / interval:7.2f}")
        print()


if __name__ == "__main__":
    main()
