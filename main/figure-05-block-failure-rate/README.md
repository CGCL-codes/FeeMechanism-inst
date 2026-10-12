# Figure 5 — block failure rate at each load inflation level

Section 7.3 and Appendix C.1. A simulated load trajectory is mapped onto an
on-chain consensus outcome, namely the probability that a CometBFT block fails
to gather two thirds of the votes and its round advances. The mapping is
estimated separately for Cosmos Hub and Osmosis from each chain's own block
history, then applied to the per-block load distribution of simulated
trajectories. The stars mark each chain's deployed configuration from Table 2.

Output: `figures/fig_failure_rate_combined.{pdf,png}`, two stacked panels
sharing the inflation axis.

## Structure

```
plot_figure5.py                 builds the figure from the mapping, the sweep and the two traces
build_mapping.py                rebuilds data/F_100bin.csv from the two censuses
data/F_100bin.csv               each chain's load-to-failure mapping, one hundred bins
cosmoshub/                      Cosmos Hub era-4 consensus census
osmosis/                        Osmosis consensus census
simulation-inflation-levels/    the inflation-level sweep and the deployed traces
```

## Reproduce the figure

```bash
python3 plot_figure5.py
```

Expected output:

```
6300 samples over 63 levels, full-block share up to 52.74%
Cosmos Hub
  deployed: inflation 0.85%, failure 2.41% (14.5x the on-chain 0.166%)
  at the 6.27% bound: failure 9.08% (54.7x)
  at 1% inflation: failure 4.75% (28.6x)
  at zero inflation: failure 0.59%
Osmosis
  deployed: inflation 1.88%, failure 12.50% (2.4x the on-chain 5.25%)
  at the 6.27% bound: failure 20.08% (3.8x)
  at 1% inflation: failure 13.24% (2.5x)
  at zero inflation: failure 8.25%
```

These are the numbers Section 7.3 quotes. The reported statistic at a level is
the median over the 100 configurations kept there. The zero-inflation line
already sits above each chain's on-chain rate, because the simulation assumes
active demand while the two chains run below the target.

## The load-to-failure mapping

```bash
python3 build_mapping.py
```

This regenerates `data/F_100bin.csv` byte for byte from the shipped censuses.

A block fails when its first round does not gather two thirds of the votes,
which CometBFT records as a non-zero round index in the commit. Execution lies
on the critical path, so the quantity that delays a vote on block `h` is the
load of block `h-1`. The history is grouped into one hundred load bins of width
0.01. For
each bin the failures whose predecessor falls in that bin are divided by the
blocks in that bin, and the bins that are not monotone in load are pooled by
isotonic regression.

The load axis is the declared gas, `gas_wanted(h-1) / max_gas`. Cosmos chains
pack blocks by the user-declared gas, and the executed gas never reaches the top
bins, so the declared gas is the only dose whose observations cover the whole
range up to the limit. The twenty Cosmos Hub bins above 0.8 hold 1,339 blocks on
the declared dose, and the isotonic fit pools them into one level.

Each chain estimates a bin's denominator on two channels. A uniform sample of
the whole history carries the low bins, scaled to the full block count. Direct
enumeration of the high-load blocks carries the top bins, where the sample holds
too few blocks to resolve a rate. The switch sits at 0.5 on Cosmos Hub and at
0.2 on Osmosis.

| chain | inputs |
|---|---|
| Cosmos Hub | `cosmoshub/data/census_era4/gas.csv`, `commits_flagged.jsonl`, `_sys_heights_stride50.npy` |
| Osmosis | `osmosis/data/census_osmosis/{gas_hiload,gas_events_sample}.csv`, `_event_heights.npy`, `_event_sample.json`, `commits_flagged.jsonl`, `osmosis/data/ibc_gas_share_osmosis.csv` |

`_sys_heights_stride50.npy` holds 190,302 systematic heights, one every 50
blocks, and is the unbiased denominator for the Cosmos Hub low bins. `gas.csv`
itself is a mixed sample and is not, which is why the denominator comes from the
height list rather than from `gas.csv` as a whole.

## The censuses

**Cosmos Hub.** An exhaustive census of era 4, heights 22,848,761 – 32,363,858
(9,515,098 blocks, 2024-10-30 to 2026-08-05, `max_gas` 75M), collected from a
public `cosmoshub-4` archive endpoint and cross-validated against an independent
node. Per candidate height the census reads `/commit` for the round and the
per-validator `block_id_flag`, and `/block_results` for gas wanted and used. It
finds 15,831 failures, a baseline rate of 0.166%.

```bash
python3 cosmoshub/collect/census_era4.py          # census + stride-100 systematic sample
python3 cosmoshub/collect/census_era4_offset50.py # offset-50 half of the stride-50 sample
python3 cosmoshub/collect/census_expand_hiload.py # seeded expansion of high-load regions
```

The expansion pass seeds on every known height at or above 50% packing and walks
outward until 30 consecutive blocks fall below 35%, so high-load spells are
covered contiguously rather than only where the systematic sample lands.

**Osmosis.** Osmosis block intervals separate cleanly. A normal block follows
its predecessor within about 2.3 seconds, while a failed round pushes the
interval past 3.4 seconds, with an empty band between. A 2.5-second threshold
therefore flags every missed round, and the pilot confirmed the separation
against `/commit` (1,070/1,070 caught, 0/18,930 false below threshold). The
result is 10,186,290 blocks between 2026-03-24 and 2026-08-06 carrying 534,882
failures, a baseline rate of 5.25%.

```bash
python3 osmosis/collect/sweep_range.py
python3 osmosis/collect/precompute_intervals.py
python3 osmosis/collect/pilot_commits.py
python3 osmosis/collect/census_osmosis_run.py
```

## The inflation levels

`simulation-inflation-levels/data/random_q20_*.csv` hold randomly sampled
Pathway-1 configurations. Each row carries its `(epsilon, alpha, delta)`, its
realized load inflation, and its load histogram over the 50,000 measured blocks,
on the same one hundred bins of width 0.01 that the mapping uses.
The parameters are drawn uniformly from `alpha` in [0.01, 0.99], `epsilon` in
[0, 16] and `delta` in [0.001, 0.125], which are the ranges Section 7.3 states.
The histogram is a sufficient statistic, because the mapping is piecewise
constant on the bins.

The plotter keeps 100 configurations at each 0.1% level from 0 to 6.2%, which is
the 6,300 samples of Section 7.3. The sweep histogram and the mapping share the
same grid, so the plotter contracts the two directly.

From the artifact root, after `./build.sh`:

```bash
python3 main/figure-05-block-failure-rate/simulation-inflation-levels/orchestrate_sweep.py
```

The orchestrator draws a first uniform batch, then refills any 0.1% level that
random draws underfill by jittering the parameters of nearby samples. A level
that two consecutive rounds fail to grow is declared unreachable and dropped.
Every batch is one `bin/random-sample -uniform-bins 100` call, and each call is
deterministic in its parameter file. The flag is what puts the histogram on the
mapping's grid, so a rerun without it would emit the simulator's default census
edges instead.

`traces/hub_final_trace.csv` and `traces/osmo_final_trace.csv` are the deployed
trajectories that carry the two stars. They come from `bin/deployed-chain` at
each chain's measured inbound ratio and delay, and their generation is documented
in `../../appendix/table-02-deployed-configurations/README.md`.

## Not shipped

Two raw block-header dumps are too large to ship: the Cosmos Hub era-4 header
dump (672 MB) and the Osmosis header sweep (714 MB). Neither is needed. What the
estimators take from them is shipped in derived form, namely
`_sys_heights_stride50.npy` for the Cosmos Hub denominator and `gas_hiload.csv`
for the Osmosis high-load screen, so `build_mapping.py` and `plot_figure5.py`
run from what is here. The dumps are re-collectable with the `collect/` scripts
above, which read and write the shipped `*/data/census_*` directories, resume
from whatever is already there, and can be run from any working directory.
