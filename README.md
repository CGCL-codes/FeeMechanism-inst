# On the (In)stability of Adaptive Fee Mechanisms in Multi-Chain Systems — Evaluation Artifact

This artifact contains the code and data behind every experimental figure and table
of the paper. 
It is organised by paper element: `main/` holds the main paper, `appendix/` holds the
appendix, and one directory corresponds to one set of experiments. `simulator/` holds the
multi-chain EIP-1559 simulator shared by every simulation experiment, and
`mext-criterion/` holds the exact stability criterion shared by every boundary figure.

## Layout

```
simulator/                     multi-chain EIP-1559 simulator, shared by every experiment
mext-criterion/                exact stability criterion rho(M_ext) < 1
figure-style/                  the shared rendering of every boundary map, Figure 4a's contract
main/                          figures and tables of the main body
appendix/                      figures and tables of the appendix
build.sh                       compiles the simulator into bin/
```


### Inside each figure directory

```
<figure>/
  README.md          what the figure shows, the command, and the numbers it should print
  *.py               plotting and analysis entry points
  data/              the raw results the scripts consume
  figures/           created on the first run, rendered PDFs are not distributed
```

## Requirements

- Go 1.24 or newer (the simulator has no dependency beyond `gopkg.in/yaml.v3`)
- Python 3.9 or newer

```bash
pip install -r requirements.txt
```

`numpy`, `pandas`, `matplotlib`, `pyyaml`, and `requests` are needed by the plotting and analysis scripts.

## Build the simulator

Every simulation experiment uses the same binaries. Build them once into `bin/`.

```bash
./build.sh
```

This produces twelve entry points, one per experiment family.

| binary | what it drives |
|---|---|
| `boundary-sweep` | the Figure 4a and 4c grids, under all three latency shapes |
| `appendix-sweep` | the Figure 9, 10, 12 and 13 grids |
| `nonuniform-2d` | the three Figure 6 grids |
| `varying-elasticity` | the three price-dependent shapes of Figure 14 |
| `mitigation-sweep` | the two compensated grids and the `gamma` scan of Figure 16 |
| `mitigation-deployed` | the per-chain `gamma` scan of Table 3 |
| `deployed-chain` | Table 2's per-chain rate sweep and its trace at the deployed rate |
| `random-sample` | the sampled inflation levels of Figure 5 |
| `kappa-fees` | one base-fee trajectory per point of Figures 7 and 8 |
| `mempool-windows` | the long-horizon window scan of Figure 15 |
| `mempool-check` | single grid points at a chosen pool bound |
| `simulate` | one trajectory from a `config.yml`, the shared single-run entry point |

## Replot every figure from the shipped data

Regenerating the figures from `data/` takes a few minutes in total and needs no
simulation run. From the artifact root:

```bash
( cd main/figure-01-fee-dynamics            && python3 plot_fee_dynamics.py )
( cd main/figure-04-stability-boundary      && python3 plot_figure4.py )
( cd main/figure-05-block-failure-rate      && python3 plot_figure5.py )
( cd main/figure-06-nonuniform-update-rate  && python3 plot_inflation_maps.py )
( cd appendix/figure-07-08-kappa-amplification && python3 plot_kappa_curves.py )
( cd appendix/figure-09-attack-channels     && python3 plot_boundary.py --figure fig9-top    --input-dir data/delayed-channel       --output-dir figures \
                                            && python3 plot_boundary.py --figure fig9-bottom --input-dir data/instantaneous-channel --output-dir figures )
( cd appendix/figure-10-instantaneous-channel-dmax1 && python3 plot_boundary.py --figure fig10 --input-dir data --output-dir figures )
( cd appendix/figure-11-latency-shapes      && python3 plot_stable_region.py && python3 plot_delta_safe.py )
( cd appendix/figure-12-varying-dmax        && python3 plot_boundary.py --figure fig12 --input-dir data --output-dir figures )
( cd appendix/figure-13-varying-chain-count && python3 plot_boundary.py --figure fig13 --input-dir data --output-dir figures )
( cd appendix/figure-14-varying-elasticity-boundary && python3 plot_delta_safe_shapes.py )
( cd appendix/figure-15-mempool-sensitivity && python3 plot_mempool_panels.py )
( cd appendix/figure-16-mitigation          && python3 plot_mitigation.py )
```

None of these needs `./build.sh`. Every script reads the CSVs shipped beside it and
prints the numbers its own README lists. Figures 2 and 3 are drawn in TikZ inside the
paper and have no directory here.


## Rerun the simulations

The boundary sweeps are the expensive part. Each `boundary-sweep` figure evaluates
3 x 15,939 nonlinear trajectories, and each `appendix-sweep` figure evaluates between
1 and 6 such grids. Expect tens of minutes to a few hours per figure
on a workstation, scaling with `-workers`. The per-figure READMEs give the exact
commands.

Every Go sweep is deterministic. The same command on the same input produces a
byte-identical CSV, and the shipped CSVs were produced by exactly these commands. 

## Common protocol

All simulation experiments share one protocol, defined in `simulator/experiments/`.

| parameter | value |
|---|---|
| horizon | 100 blocks of warm-up, then the 50,000 measured blocks (50,100 in total) |
| load statistics | `avg_load`, `load_std`, `load_inflation` and `full_block_fraction` cover the 50,000 measured blocks only, so block 100 to block 50,099 |
| target load | 0.5 of the gas limit |
| gas limit | 2,000,000 per chain |
| transaction pool | bounded at 20x the block gas limit per chain, matching the default pool sizes of geth, CometBFT and Substrate |



## Experiment settings

Three chains unless stated otherwise. Every chain has a 2,000,000 gas limit and a
target load of 0.5, so each carries 1,000,000 gas of demand at equilibrium. `alpha` is
the cross-chain share of that demand.

### Load topologies

**Inbound-coupled** (Figures 4, 7, 8, 11, 12, 13, 14, 15 and 16, Tables 2 and 3,
Figure 9's top row, and the inflation levels of Figure 5). Chain 0 receives
cross-chain load and sends none.

| | local | outbound | inbound |
|---|---|---|---|
| Chain 0 | `(1-alpha)` | none | `alpha`, split evenly across the `N-1` peers |
| Peer j | `(1-alpha)` | `alpha/(N-1)` to Chain 0, `alpha/(2(N-1))` to each other peer | from the other peers |

**Outbound-coupled** (Figure 9's bottom row and Figure 10). The direction is reversed.
Chain 0 sends `alpha/2` to each peer and receives nothing. Each peer keeps `(1-alpha)`
local and sends `alpha/4` to the other peer.

**Fixed** (Figure 6). Chain 0 carries an inbound ratio of 0.8, split evenly
across the two peers. Three variants differ in Chain 0's outbound share and in the
source-side elasticity. See that figure's README.

Elasticities default to 1.5 everywhere. Each experiment raises exactly one family:

| raised | meaning | used by |
|---|---|---|
| `epsilon[j][0]` | destination-side elasticity of inbound flows | Figures 4, 5, 7, 11, 12, 13, 14, 15 and 16, Tables 2 and 3 |
| `lambda[j][0]` | source-side elasticity of inbound flows | Figures 8 and 9 top row |
| `epsilon[0][j]` | destination-side elasticity of Chain 0's outbound flows | Figure 9 bottom row, Figure 10 |

Figures 7 and 8 are the pair that shares a topology but splits the elasticity: both
sweep the inbound-coupled system, Figure 7 raising `epsilon[j][0]` to measure
`kappa_def` and Figure 8 raising `lambda[j][0]` to measure `kappa_att`.

Unless a figure's README says otherwise, a sweep starts at the equilibrium load and
applies a one-block demand shock to Chain 0 at the end of warm-up, with multiplier
1.01. A point counts as converged when every one of the final 50 measured loads sits
within 0.1% of the target. Cross-chain delay weights come in three shapes: spike
`[0,0,0,0,1]`, uniform `[0.2,...,0.2]` and bimodal `[0.4,0,0.2,0,0.4]`.

### Per-figure grids

| figure | fixed | swept | grid |
|---|---|---|---|
| 4a | `delta = 0.125`, `d_max = 5` | `epsilon_j0` 0→16 step 0.1, `alpha_in` 0.01→0.99 step 0.01 | 15,939 |
| 4c | `epsilon_j0 = 16`, `d_max = 5` | `delta` 0.001→0.125 step 0.001, same `alpha_in` | 12,375 |
| 5 | `d_max = 5` spike | `epsilon_j0`, `alpha_in` and `delta` drawn uniformly from `[0, 16]`, `[0.01, 0.99]` and `[0.001, 0.125]` | 32,872 drawn, 100 kept per 0.1% inflation level from 0 to 6.2%, so 6,300 |
| 6 | `d_max = 5` spike, inbound ratio 0.8, `epsilon = 16` on every cross-chain flow | `delta_0` and `delta_peer` over `[0.001, 0.125]` step 0.001 | 15,625 x 3 configurations |
| 7 | `delta = 0.125`, `d_max = 5` | `epsilon_j0` 0→16 step 0.5, `alpha_in` mapped linearly onto `[0.01, 0.99]` | 33 x 3 shapes |
| 8 | `delta = 0.125`, `d_max = 5` | `lambda_j0` 0→16 step 0.5, same `alpha_in` mapping | 33 x 3 shapes |
| 9 top | `delta = 0.125`, `d_max = 5` | `lambda_j0` 0→16 step 0.1, `alpha_in` | 15,939 x 3 shapes |
| 9 bottom | `delta = 0.125`, `d_max = 5` | `epsilon_0j` 0→16 step 0.1, `alpha_out` | 15,939 x 3 shapes |
| 10 | `delta = 0.125`, **`d_max = 1`** | `epsilon_0j`, `alpha_out` | 15,939 |
| 11 | same as 4a and 4c | same, under bimodal and uniform latency | 15,939 + 12,375 |
| 12 | `delta = 0.125`, **`d_max` in {5, 7, 10}** | `epsilon_j0`, `alpha_in` | 15,939 per shape per delay |
| 13 | `delta = 0.125`, `d_max = 5` spike, **`N` in {5, 7, 10}** | `epsilon_j0`, `alpha_in` | 15,939 per chain count |
| 14 | `d_max = 5` spike, `epsilon_j0(x)` one of three price-dependent shapes with `eps(1) = 16` | the 4c grid per shape | 12,375 x 3 shapes |
| 15 | `delta = 0.125`, `d_max = 5` spike, **pool bound `Q` in {10, 20, 50, 100}** | the 4a grid per pool bound | 15,939 x 4 |
| 16 | `d_max = 5` spike, compensated with `H_i = gamma * Lambda_i^delay` | the 4a and 4c grids at `gamma = 1`, plus `gamma` 0->1.5 step 0.005 x `delta` 0.001->0.2 step 0.001 at `alpha_in = 0.99`, `epsilon_j0 = 16` | 15,939 + 12,375 + 60,200 |
| Table 2 | deployed `alpha` and `d_max` per chain, `epsilon_j0 = 16` | `delta` 0.001→0.300 step 0.001, plus one trace at the deployed `delta` | 300 x 6 chains |
| Table 3 | deployed `alpha` and `d_max` (Table 2), `epsilon_j0 = 16`, deployed `delta` | `gamma` 0->3 step 0.01 | 301 x 2 |

### Worked example: two points of the Figure 4a grid

Each grid point rebuilds the demand and elasticity matrices from scratch. Chain 0 always
carries `1,000,000` gas of demand at equilibrium, and `alpha` decides how much of it
arrives from the two peers.

**Point A: `epsilon_j0 = 16.0`, `alpha = 0.99`.** Chain 0 keeps `10,000` gas of local
demand and receives `990,000` from the peers, `495,000` from each. Each peer keeps
`10,000` local and sends `247,500` to the other peer.

```
demand (gas)      to 0      to 1      to 2
     from 0     10,000         0         0
     from 1    495,000    10,000   247,500
     from 2    495,000   247,500    10,000

epsilon = [[  0, 1.5, 1.5]      lambda = [[1.5, 1.5, 1.5]
           [ 16,   0, 1.5]                [1.5, 1.5, 1.5]
           [ 16, 1.5,   0]]               [1.5, 1.5, 1.5]]
```

Only the two inbound entries of the elasticity matrix carry the swept value. This point
does not converge. Its realized load inflation is `6.2149%` and `rho(M_ext)` is `1.2767`.
It fills `52.45%` of its blocks to the gas limit.

**Point B: `epsilon_j0 = 4.0`, `alpha = 0.50`.** Chain 0 keeps `500,000` local and
receives `500,000`, `250,000` from each peer. Each peer keeps `500,000` local and sends
`125,000` to the other peer.

```
demand (gas)      to 0      to 1      to 2
     from 0    500,000         0         0
     from 1    250,000   500,000   125,000
     from 2    250,000   125,000   500,000

epsilon = [[  0, 1.5, 1.5]      lambda = [[1.5, 1.5, 1.5]
           [  4,   0, 1.5]                [1.5, 1.5, 1.5]
           [  4, 1.5,   0]]               [1.5, 1.5, 1.5]]
```

This point converges. Its load inflation is `0.0000%` and `rho(M_ext)` is `0.9473`. It
never fills a block.

Everything else is identical between the two points, including `delta = 0.125`,
`d_max = 5`, the spike delay weights `[0,0,0,0,1]`, and the one-block `1.01x` shock. The
sweep walks `epsilon_j0` from 16.0 down to 0.0 in steps of 0.1 and, for each value,
`alpha` from 0.99 down to 0.01 in steps of 0.01. That is the 15,939 points of Figure 4a.

Figures 4, 11, 12, 13 and 15 all come from the same two sweep definitions. They differ
only in latency shape, delay window, chain count and pool bound.

### Figures 7 and 8

These two do not search a convergence boundary. They sweep one elasticity from 0 to 16
in steps of 0.5, with the inbound ratio mapped linearly onto `[0.01, 0.99]`, and for
each point measure an amplification ratio over the trajectory rather than a pass/fail
verdict. Both use the inbound-coupled topology, so Chain 0's load is `(1-alpha)` local
and `alpha` inbound, split evenly. Figure 7 raises `epsilon[j][0]` and Figure 8 raises
`lambda[j][0]`. `bin/kappa-fees` builds both matrices from scratch at every point and
returns the three chains' base-fee trajectories, and the two kappa definitions are
applied in Python.

The reported statistic is the **90th percentile** of the per-step kappa series. Kappa
divides a past deviation by the current one, so the ratio diverges on the steps where
the current deviation crosses zero. The mean and the maximum are both dominated by those
isolated steps. The 90th percentile is not.

### Deployed-rate evaluation (Table 2, Section 7.3)

This experiment turns Table 2's measurements into a stability verdict. Each of the
six chains is rerun in the simulator under its measured configuration: the deployed
`alpha` and `d_max`, with inbound elasticity 16. For every chain the sweep walks
`delta` from 0.001 to 0.300 in steps of 0.001 and reports the largest stable value,
the chain's maximum stable update rate. Comparing that bound against the deployed
`delta` gives the verdict. The four Polkadot chains sit far inside their bounds.
Asset Hub stops at 0.163, Hydration at 0.166, and Bifrost past the 0.300 end of the
scan, against a deployed 7.5e-5 on all three. Moonbeam stops at 0.062 against a
deployed 0.004. Cosmos Hub (bound 0.056, deployed 0.125) and Osmosis (bound 0.019,
deployed 0.1) sit outside theirs. Each chain then runs once more at its deployed rate,
and the realized load inflation over the 50,000 measured blocks is the number
Section 7.3 quotes: 0.85% on Cosmos Hub, 1.88% on Osmosis, and 0.00% on every
Polkadot chain.
The commands and the expected output live in
`appendix/table-02-deployed-configurations/README.md` under `deployed-update-rate/`.
The two unstable trajectories double as the star markers of Figure 5.



## Data availability

Two raw block dumps of two chains are too large to include in the artifact. Both are
re-collectable from public archive RPC endpoints with the census scripts under
`main/figure-05-block-failure-rate/*/collect/`.

Figure 1's raw per-block fee scan,
`main/figure-01-fee-dynamics/data/<chain>_<date>/<chain>_fee_range_<date>.csv`, is
written by `fetch_fee.sh` and consumed by `compute_fee_load_metrics.py`, so
re-collecting Figure 1 runs both steps in order. The merged fee-load CSV that the
plotter reads is shipped.

Every input of every figure is included, and each figure directory's README lists the
exact command and the numbers it should print.

## License

The artifact is released under the Apache License 2.0 (`LICENSE`, mirrored at
`simulator/LICENSE`).
