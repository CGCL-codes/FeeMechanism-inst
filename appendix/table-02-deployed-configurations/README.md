# Table 2 — Empirical configuration of representative parachains and zones

Appendix C, with the stability consequences reported in Section 7.3. The table gives,
per chain, the total cross-chain gas ratio, the inbound ratio, the deployed EIP-1559
update rate, and the cross-chain latency in destination-chain blocks.

| chain | total ratio | inbound ratio | delta | d_max |
|---|---|---|---|---|
| Asset Hub | 27.4% | 13.4% | 7.5e-5 | 7 |
| Bifrost | 18.6% | 6.0% | 7.5e-5 | 7 |
| Hydration | 21.6% | 13.3% | 7.5e-5 | 7 |
| Moonbeam | 43.3% | 25.5% | 0.004 | 7 |
| Cosmos Hub | 23.9% | 21.6% | 0.125 | 10 |
| Osmosis | 26.1% | 24.8% | 0.1 | 25 |

## What is measured here and what is cited

The Cosmos rows are measured on-chain by the scripts in this directory. The Polkadot
rows are not: their traffic ratios come from Subscan, their update rates from runtime
source and protocol documentation, and their cross-chain latency from the empirical
cross-parachain latency study by Fujihara et al. cited in the paper's Appendix C.
Those sources are given in the table's footnotes and no code accompanies them.

## Cross-chain ratio

Every Cosmos transaction's gas is recoverable on-chain, so the ratio is measured in gas
rather than message count. Each sampled block's executed gas is split by the IBC message
types its transaction bodies carry. Packet-receive transactions are the destination side
of an inbound flow. Client updates, acknowledgements and timeouts are IBC
infrastructure. Outbound transfers are the source side of an outbound flow. Everything
else is local. The inbound ratio of Table 2 is the first two classes and the total
cross-chain ratio adds the third.

```bash
python3 cross-chain-ratio/analyze_gas_share.py
```

Output:

```
=== Cosmos Hub (the 2025 calendar year) ===
  68,865 rows on file, 60,000 inside the window
  packet-receive      12.9%
  IBC infrastructure   8.7%
  outbound             2.4%
  inbound ratio       21.6%
  total cross-chain   23.9%

=== Osmosis (April 15 to August 6, 2026) ===
  83,252 rows on file, 80,000 inside the window
  packet-receive      15.7%
  IBC infrastructure   9.1%
  outbound             1.3%
  inbound ratio       24.8%
  total cross-chain   26.1%
```

Those are the two Cosmos rows of the table. `cosmoshub_ibc_gas_share.csv` and
`osmosis_ibc_gas_share.csv` hold the per-block breakdown, one row per sampled height,
with executed and declared gas per class. The analyzer restricts each file to its
chain's window, heights 23,763,459 to 29,114,836 on Cosmos Hub and 59,405,170 to
67,958,290 on Osmosis, and reports shares of executed gas.

The ratio cannot be censused, because classifying it needs one block call plus one
block-results call per height. `measure_ibc_gas_share.py` and
`measure_ibc_gas_share_osmo.py` are the original seeded 20,000-height samplers, and
`expand_gas_share.py` is the pass that grew the in-window sample to the 60,000 and
80,000 heights above. All three fetch from public archive endpoints and skip heights
already on file. `expand_gas_share.py` reads and appends to the two shipped CSVs in
place, so rerunning it on the shipped files finds the target already met and fetches
nothing.

## Cross-chain latency

An IBC packet carries a channel identifier and a sequence number, so a receive on the
destination chain matches exactly one send on the source chain. The destination-side
record does not carry the send time, but it carries the packet's timeout, and relayers
set that timeout from one of three standard windows of 300, 600 and 1200 seconds. The
margin between the timeout and the receive time therefore recovers the elapsed delay as
the window minus the margin. A packet whose margin falls outside every window uses a
non-standard timeout and is dropped. The delay in destination-chain blocks is the
elapsed time divided by the chain's realized mean block interval.

```bash
python3 cross-chain-latency/analyze_delays.py
```

Output:

```
=== Cosmos Hub (January 1 to December 31, 2025) ===
  rows 1,173,366  usable 822,514  channels 102
  mean 10.07 blocks  CI [10.03, 10.11]   d_max = 10
  mean seconds 59.3  block interval 5.8931 s
  channel        packets   share   mean(blk)
    channel-141   388,153   47.2%      7.91
    channel-569    96,048   11.7%     17.17
    channel-91     45,893    5.6%      4.08
    channel-1351   34,136    4.2%      5.71
    channel-339    28,634    3.5%      9.88
    (97 others)   229,650   27.9%     12.61

=== Osmosis (April 15 to August 6, 2026) ===
  rows 341,859  usable 286,717  channels 119
  mean 25.47 blocks  CI [25.31, 25.65]   d_max = 25
  mean seconds 29.2  block interval 1.1478 s
  channel        packets   share   mean(blk)
    channel-105897  135,225   47.2%     16.80
    channel-0      27,265    9.5%     28.76
    channel-750    24,809    8.7%     46.88
    channel-101635   11,875    4.1%     17.89
    channel-208     9,528    3.3%     51.38
    (114 others)   78,015   27.2%     30.51
```

`d_max` is the pooled mean over every usable packet, rounded. It is 10 blocks on Cosmos
Hub and 25 on Osmosis. The bracket is a 500-resample bootstrap of that mean, and it is
narrow enough that neither value is in doubt.

The two `.csv.gz` files are the full packet censuses of their windows, not samples. The
Cosmos Hub file covers every `recv_packet` event of the 2025 calendar year, 1,173,366
events over 950,186 distinct heights, of which 822,514 use a standard timeout window.
The Osmosis file covers April 15 to August 6, 2026, 341,859 events over 315,815 heights,
of which 286,717 are usable. Each row is one event, recording the height, the block
time, the sequence number, the source channel, and the margin in seconds.

Traffic is concentrated. One channel carries 47.2% of the packets on each chain, and it
is the faster half of the distribution on both: 7.91 blocks on Cosmos Hub against the
12.61-block mean of the 97 smallest channels, and 16.80 blocks on Osmosis against 30.51.
Taking the pooled mean rather than the busiest channel is therefore the conservative
choice.

`cross-chain-latency/collect_recv_packets.py` is the collector. It reads heights from
the census header dumps, which are the same unshipped dumps described in
`main/figure-05-block-failure-rate/README.md`, requests one `block_results` per height,
and writes every `recv_packet` event to `recv_delays_hub.csv` or `recv_delays_osmo.csv`
in the schema above. Its `N_HEIGHTS` constant caps a rerun at a seeded 20,000-height
draw, so rerunning it reproduces a sample of the shipped censuses rather than the
censuses themselves.

## Fee parameters

`fee-parameters/` holds the Cosmos Hub feemarket module's on-chain parameters and
state, which confirm the deployed `delta = 0.125` and the 75M gas limit used to
normalize load. `cosmoshub_feemarket_params.json` pins `min_learning_rate` and
`max_learning_rate` to 0.125 and `max_block_utilization` to 75,000,000.
`cosmoshub_feemarket_aligned.json` is a run of consecutive heights carrying the
per-block learning rate, which stays at 0.125 throughout.

## Deployed-rate evaluation (Section 7.3)

Each chain's configuration is rerun in the simulator under the same elasticity 16 as
Ethereum, to find its maximum stable update rate and its load inflation at the deployed
rate. The surrogate is the inbound-coupled three-chain system of Figure 4, with the
chain's measured inbound ratio, spike latency at its measured `d_max`, and the Section
7.1 protocol.

From the artifact root, after `./build.sh`:

```bash
cd appendix/table-02-deployed-configurations/deployed-update-rate
./run_all.sh
```

`run_all.sh` finds the binary at `../../../bin/deployed-chain` by default. Override
with the `DEPLOYED_CHAIN_BIN` environment variable if it lives elsewhere. The six runs
together take about a minute.

Each invocation sweeps `delta` from 0.001 to 0.300 to locate the boundary, then dumps
the 50,000-block post-shock trace at the deployed rate. Expected results:

| chain | alpha | d_max | max stable delta | deployed delta | inflation at deployed rate |
|---|---|---|---|---|---|
| Asset Hub | 0.134 | 7 | 0.163 | 7.5e-5 | 0.00% |
| Bifrost | 0.060 | 7 | > 0.300 | 7.5e-5 | 0.00% |
| Hydration | 0.133 | 7 | 0.166 | 7.5e-5 | 0.00% |
| Moonbeam | 0.255 | 7 | 0.062 | 0.004 | 0.00% |
| Cosmos Hub | 0.216 | 10 | 0.056 | 0.125 | 0.85% |
| Osmosis | 0.248 | 25 | 0.019 | 0.1 | 1.88% |

Bifrost never destabilizes inside the swept range, which the run reports as a first
unstable rate of -1. The four Polkadot chains stay far inside their bounds. Both Cosmos
chains sit outside theirs, Cosmos Hub by a factor of 2.2 and Osmosis by a factor of 5.3.

`traces/` holds the six trajectories, each 50,000 blocks measured after the 100 warm-up
blocks. The two Cosmos traces are the unstable ones and they carry the star markers of
Figure 5. On `cosmoshub_delta0.125_dmax10.csv` load swings between 0.244 and 0.838 and
no block reaches the gas limit. On `osmosis_delta0.1_dmax25.csv` load swings between
0.050 and the gas limit itself, and 15.6% of blocks sit at that limit.
