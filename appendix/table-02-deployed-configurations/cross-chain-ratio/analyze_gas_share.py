"""Table 2's cross-chain ratio, measured in executed gas.

Appendix C.2. A message-count proxy overcounts, because an XCM message does not
map one to one onto a sub-transaction and an IBC packet batches transfers. On
Cosmos chains every transaction's gas and message types are recoverable on
chain, so the ratio is measured directly in gas.

Each sampled block's gas is split into four classes by the IBC message types the
transaction bodies carry:

  in    packet-receive transactions, the destination side of an inbound flow
  rel   IBC infrastructure, namely client updates, acknowledgements and timeouts
  out   outbound transfers, the source side of an outbound flow
  loc   everything else

The inbound ratio of Table 2 is `in + rel`. The total cross-chain ratio adds
`out`. Both are shares of executed gas, the `_gu` columns.
"""
import argparse
import csv
from pathlib import Path

HERE = Path(__file__).resolve().parent

CHAINS = {
    "Cosmos Hub": {
        "file": "cosmoshub_ibc_gas_share.csv",
        "window": (23_763_459, 29_114_836),
        "label": "the 2025 calendar year",
    },
    "Osmosis": {
        "file": "osmosis_ibc_gas_share.csv",
        "window": (59_405_170, 67_958_290),
        "label": "April 15 to August 6, 2026",
    },
}

CLASSES = ("in", "rel", "out", "loc")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=HERE)
    args = parser.parse_args(argv)

    for name, config in CHAINS.items():
        path = args.data_dir / config["file"]
        if not path.exists():
            print(f"{name}: {config['file']} missing, skipped\n")
            continue
        low, high = config["window"]
        rows = [row for row in csv.DictReader(open(path))]
        sampled = [row for row in rows if low <= int(row["height"]) <= high]
        total = sum(int(row[f"{key}_gu"]) for row in sampled for key in CLASSES)
        share = {key: 100 * sum(int(row[f"{key}_gu"]) for row in sampled) / total
                 for key in CLASSES}

        print(f"=== {name} ({config['label']}) ===")
        print(f"  {len(rows):,} rows on file, {len(sampled):,} inside the window")
        print(f"  packet-receive     {share['in']:5.1f}%")
        print(f"  IBC infrastructure {share['rel']:5.1f}%")
        print(f"  outbound           {share['out']:5.1f}%")
        print(f"  inbound ratio      {share['in'] + share['rel']:5.1f}%")
        print(f"  total cross-chain  {share['in'] + share['rel'] + share['out']:5.1f}%")
        print()


if __name__ == "__main__":
    main()
