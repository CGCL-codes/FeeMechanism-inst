# Figure 1 — Fee dynamics on Ethereum and Moonbeam

Section 4.1. Ethereum's base fee tracks the effective gas price continuously, while
Moonbeam's near-static base fee leaves price discovery to priority tips. The figure is
delivered as two files, which the paper stacks into one four-panel figure.

| paper | output of `plot_fee_dynamics.py` | content |
|---|---|---|
| upper panels | `figures/figure-01-top-fee-trajectories.pdf` | the full-day fee paths |
| lower panels | `figures/figure-01-bottom-price-anchor.pdf` | base fee against effective gas price, top 10% of blocks by load |

## Data

| file | contents |
|---|---|
| `data/eth_2025-12-23/eth_fee_load_2025-12-23.csv` | 7,158 Ethereum blocks, 24071593 – 24078750, 2025-12-23 UTC |
| `data/moonbeam_2025-03-21/moonbeam_fee_load_2025-03-21.csv` | 14,203 Moonbeam blocks, 10105108 – 10119310, 2025-03-21 UTC |

Both files carry the same nine columns.

| column | unit | meaning |
|---|---|---|
| `chain` | — | `eth` or `moonbeam` |
| `timestamp` | UTC | block time |
| `block` | — | block number |
| `base_fee_gwei` | gwei | the block's base fee |
| `effective_gas_price_gwei` | gwei | the block's effective gas price |
| `gas_used` | gas | gas consumed by the block |
| `gas_limit` | gas | gas limit of that block |
| `load` | fraction | `gas_used / gas_limit` |
| `tx_count` | — | transactions in the block |

There is no priority-tip column. The tip is already folded into
`effective_gas_price_gwei`, and the two chains fold it differently. Ethereum is read
through `eth_feeHistory`, so its effective gas price is the base fee plus the block's
median priority tip. Moonbeam is read with a full per-block transaction scan, so its
effective gas price is the median over the block's transactions of the price actually
paid, floored at the base fee. A Moonbeam block with no transactions falls back to its
base fee.

Nothing on disk is normalized. The two fee columns are raw gwei and `load` is a raw
ratio. Normalization happens in `plot_fee_dynamics.py`, which divides both fee columns
by the smallest base fee that chain shows during its day, 0.019917168 gwei for Ethereum
and 31.25 gwei for Moonbeam. Those ratios are what the panels draw and they exist only
inside the script.

The Moonbeam file ends on a boundary row. Block 10119310 is stamped
2025-03-22T00:00:00Z, the closing instant of the fetch window, and it carries the fee
pair but empty `gas_used`, `gas_limit`, `load` and `tx_count`. So 14,203 rows carry
fees and 14,202 of them carry a load. The lower panel drops the row, because an empty
load never clears the top-decile threshold. The upper panel keeps it. Its hour of day
is zero, so the two Moonbeam curves close with one segment running back to the left
edge along the 1x line, where the base fee already sits. The Ethereum file has no such
row.

`data/eth_2025-12-23/eth_fee_load_metrics_2025-12-23.json`,
`data/moonbeam_2025-03-21/moonbeam_fee_load_metrics_2025-03-21.json` and
`data/fee_load_metrics_moonbeam_eth.json` are run logs of
`compute_fee_load_metrics.py`, not inputs. Each `outputs` block names four files, of
which only the fee-load CSV is shipped. The figure consumes that CSV alone, and the
top-decile thresholds and correlations the logs record are the ones
`plot_fee_dynamics.py` recomputes from it.

The other three are intermediates of `compute_fee_load_metrics.py`. Nothing reads the
1-minute CSV or the top-10% CSV. The load CSV is different, because the script both
writes it and reads it back. On a re-collection it skips the per-block gas fetch
whenever that file is already present, so it acts as a cache. A stale copy would
therefore change what a re-collection produces, which is why none is shipped.

## Reproduce the figure

```bash
python3 plot_fee_dynamics.py
```

Expected output:

```
Ethereum (2025-12-23): top-decile n=716, load threshold=0.889377, rho_anchor=0.974058
Moonbeam (2025-03-21): top-decile n=1421, load threshold=0.367402, rho_anchor=0.003901
Ethereum (2025-12-23): temporal observations above 300x=7
Moonbeam (2025-03-21): temporal observations above 300x=0
```

Two further lines report the absolute paths of the saved PDFs.

`rho_anchor` is `Corr(log B_i, log P_i)` over the top decile of blocks by load, which
the paper reports as 0.974 for Ethereum and 0.004 for Moonbeam. The count above 300x is
the number of scatter points the upper panel's axis clips. All seven are Ethereum
blocks whose effective gas price spikes past 300 times the day's smallest base fee.

## Re-collect the data

`fetch_fee.sh` replays the two collections against public JSON-RPC endpoints.
`compute_fee_load_metrics.py` then merges each fee scan with per-block gas and writes
the fee-load CSV.

```bash
export ETH_RPC_URL="https://ethereum-rpc.publicnode.com"
./fetch_fee.sh
python3 compute_fee_load_metrics.py
```

That public endpoint is the default of both `fetch_fee_range.py` and
`compute_fee_load_metrics.py`, so either runs unconfigured. Only `fetch_fee.sh` insists
on `ETH_RPC_URL` being set. Export it as above, or point it at a private endpoint.
Moonbeam's public endpoint is the default throughout.

The two steps chain through `data/<chain>_<date>/<chain>_fee_range_<date>.csv`, which
`fetch_fee.sh` writes and `compute_fee_load_metrics.py` reads. That file is an
intermediate and is not shipped, so re-collection runs both steps in order.

Both chains are sampled over a full UTC day. Moonbeam is fetched with `--force-manual`
because its node does not serve `eth_feeHistory` over the required range.
