"""Rebuild both chains' load-to-failure mappings on one hundred uniform 0.01-wide bins.

Appendix C.1. A block fails when its first round does not gather two thirds of
the votes, which CometBFT records as a non-zero round index in the commit. The
quantity that delays a vote on block h is the load of block h-1, because
execution lies on the critical path. This script groups each chain's history
into one hundred load bins of width 0.01, divides the failures whose predecessor falls in
a bin by the blocks in that bin, and pools the bins that are not monotone in
load by isotonic regression.

The load axis is the declared gas, `gas_wanted(h-1) / max_gas`. Cosmos chains
pack blocks by the user-declared gas, and the executed gas never reaches the top
bins, so the declared gas is the only dose whose observations cover the whole
range up to the limit.

Each chain estimates a bin's denominator on two channels. A uniform sample of
the whole history carries the low bins, scaled to the full block count. Direct
enumeration of the high-load blocks carries the top bins, where the sample holds
too few blocks to resolve a rate. The load at which the estimator switches is
0.5 on Cosmos Hub and 0.2 on Osmosis.

Output: `data/F_100bin.csv`, one failure probability per bin per chain.
"""
import csv
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
HUB = HERE / "cosmoshub" / "data" / "census_era4"
OSMO = HERE / "osmosis" / "data" / "census_osmosis"
OUT = HERE / "data" / "F_100bin.csv"

# Census totals, quoted in Appendix C.1.
HUB_BLOCKS = 9_515_098
OSMO_BLOCKS = 10_186_290
OSMO_EVENTS = 534_882

HUB_LIMIT = 75_000_000.0
OSMO_LIMIT = 300_000_000.0

EDGES = np.round(np.arange(0, 1.0, 0.01), 4)
EDGES = np.append(EDGES, 1.01)        # the top bin closes above the limit
NBINS = len(EDGES) - 1


def histogram(values, lo=0, hi=NBINS):
    counts = np.zeros(NBINS)
    for index in range(lo, hi):
        counts[index] = ((values >= EDGES[index]) & (values < EDGES[index + 1])).sum()
    return counts


def pava(events, blocks):
    """Weighted isotonic regression, pooling adjacent violators."""
    blocks = np.maximum(blocks, events)
    values, weights, groups = [], [], []
    for index in range(len(events)):
        weight = max(blocks[index], 1e-9)
        value, group = events[index] / weight, [index]
        while values and values[-1] >= value:
            previous, previous_weight = values.pop(), weights.pop()
            group = groups.pop() + group
            value = (value * weight + previous * previous_weight) / (weight + previous_weight)
            weight += previous_weight
        values.append(value)
        weights.append(weight)
        groups.append(group)
    fitted = np.zeros(len(events))
    for value, group in zip(values, groups):
        fitted[group] = value
    return fitted


def gas_column(path, column=1):
    """Read a census gas file into {height: declared gas}. Column 1 is GasWanted."""
    table = {}
    with open(path) as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            table[int(row[0])] = int(row[column])
    return table


def report(name, events, blocks, channel_from, fitted):
    print(f"=== {name} ===")
    print("  bin           events   denominator   channel        raw        F")
    for index in range(NBINS):
        channel = "exact census" if index >= channel_from else "uniform sample"
        raw = 100 * events[index] / max(blocks[index], 1e-9)
        print(f"  [{EDGES[index]:.2f},{EDGES[index+1]:.2f})  {events[index]:7.0f}  "
              f"{int(blocks[index]):12,}   {channel:<15} {raw:7.3f}%  {100*fitted[index]:7.3f}%")
    print()


def hub():
    """Cosmos Hub. The stride-50 systematic sample carries the low bins, and the
    seeded high-load enumeration carries the bins from 0.5 up."""
    gas = gas_column(HUB / "gas.csv")
    events = [json.loads(line) for line in open(HUB / "commits_flagged.jsonl")]
    failures = [event["h"] for event in events if 0 < event["round"] < 9]
    event_dose = np.array([gas[h - 1] / HUB_LIMIT for h in failures if h - 1 in gas])

    stride = [int(h) for h in np.load(HUB / "_sys_heights_stride50.npy") if int(h) in gas]
    stride_dose = np.array([gas[h] / HUB_LIMIT for h in stride])
    scale = HUB_BLOCKS / len(stride)
    census_dose = np.array([value / HUB_LIMIT for value in gas.values()])

    channel_from = int(np.searchsorted(EDGES, 0.5, side="right")) - 1
    counts = histogram(event_dose)
    blocks = histogram(stride_dose, 0, channel_from) * scale
    blocks += histogram(census_dose, channel_from, NBINS)
    fitted = pava(counts, blocks)
    report("Cosmos Hub", counts, blocks, channel_from, fitted)
    return fitted


def osmosis():
    """Osmosis. The byte-size screen captures every high-load block, so the bins
    from 0.2 up are exact. Below that the estimate is a uniform event sample
    against a uniform block sample, each scaled to the full census."""
    high_gas = gas_column(OSMO / "gas_hiload.csv")
    sample_gas = gas_column(OSMO / "gas_events_sample.csv")
    event_heights = np.load(OSMO / "_event_heights.npy")
    event_sample = json.load(open(OSMO / "_event_sample.json"))

    rounds = {}
    for line in open(OSMO / "commits_flagged.jsonl"):
        record = json.loads(line)
        rounds[record["h"]] = record["round"]

    # The uniform block sample that carries the low-load denominator. Only these
    # 20,000 draws span the whole census window.
    denominator = []
    with open(OSMO.parent / "ibc_gas_share_osmosis.csv") as handle:
        for row in csv.DictReader(handle):
            denominator.append((int(row["in_gw"]) + int(row["out_gw"])
                                + int(row["rel_gw"]) + int(row["loc_gw"])) / OSMO_LIMIT)
    denominator = np.array(denominator)

    high_dose = np.array([value / OSMO_LIMIT for value in high_gas.values()])
    sample_dose = np.array([sample_gas[h - 1] / OSMO_LIMIT
                            for h in event_sample if h - 1 in sample_gas])

    channel_from = int(np.searchsorted(EDGES, 0.2, side="right")) - 1
    scale_events = OSMO_EVENTS / len(event_sample)
    scale_blocks = OSMO_BLOCKS / len(denominator)

    # The exact channel counts only the events whose round index is confirmed in
    # range. A candidate that was never confirmed, or that turned out to be
    # round 0, is dropped.
    exact = np.zeros(NBINS)
    for height in event_heights:
        height = int(height)
        if height - 1 not in high_gas:
            continue
        round_index = rounds.get(height)
        if round_index is None or not 0 < round_index < 9:
            continue
        bin_index = int(np.searchsorted(
            EDGES, high_gas[height - 1] / OSMO_LIMIT, side="right")) - 1
        if 0 <= bin_index < NBINS:
            exact[bin_index] += 1

    counts = histogram(sample_dose) * scale_events
    counts[channel_from:] = exact[channel_from:]
    blocks = histogram(denominator, 0, channel_from) * scale_blocks
    blocks += histogram(high_dose, channel_from, NBINS)
    fitted = pava(counts, blocks)
    report("Osmosis", counts, blocks, channel_from, fitted)
    return fitted


def main():
    f_hub = hub()
    f_osmo = osmosis()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["bin", "lo", "hi", "F_hub", "F_osmo"])
        for index in range(NBINS):
            writer.writerow([index, EDGES[index], EDGES[index + 1],
                             f"{f_hub[index]:.8f}", f"{f_osmo[index]:.8f}"])
    print(f"[OK] wrote {OUT}")


if __name__ == "__main__":
    main()
