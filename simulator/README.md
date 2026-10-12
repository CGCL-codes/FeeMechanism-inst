# Multi-chain EIP-1559 simulator

A discrete-time nonlinear simulator of `N` chains, each running its own EIP-1559
controller, coupled by delayed cross-chain load. Prices and loads evolve
endogenously: demand responds to the current price of the chain it executes on and,
for cross-chain workflows, to the price of the counterpart chain.

## Packages

| path | contents |
|---|---|
| `core/` | the fee controller, the demand generator, the delay queue, and the observed-load summaries |
| `experiments/boundary/` | the fixed-delta and fixed-elasticity grids behind Figures 4, 11 and 15 |
| `experiments/appendix/` | the channel-strength, `d_max` and chain-count grids behind Figures 9, 10, 12 and 13 |
| `experiments/nonuniform/` | the per-chain update-rate grids behind Figure 6 |
| `experiments/mitigation/` | the compensated-controller grids behind Figure 16 |
| `cmd/` | the command-line entry points |

## Commands

`./build.sh` compiles all twelve entry points into `bin/`.

| command | produces |
|---|---|
| `simulate` | one trajectory from `config.yml`, logged block by block. No figure depends on it |
| `boundary-sweep -figure fig4a\|fig4c` | the two stability-boundary grids, one CSV per latency shape |
| `appendix-sweep -figure <id>` | the channel-strength, `d_max` and chain-count grids, one CSV per scenario |
| `nonuniform-2d -job <name>` | the three per-chain update-rate grids of Figure 6 |
| `varying-elasticity -shape <shape>` | the Figure 14 boundary grid under a price-dependent inbound elasticity |
| `mitigation-sweep -mode fig4a\|fig4c\|gamma` | the two grids and the gamma scan under the compensated controller, for Figure 16 |
| `mitigation-deployed` | the stable gamma interval at each deployed chain's update rate, for Table 3 |
| `deployed-chain <alpha> <dmax> <delta> <out.csv>` | the maximum stable update rate and the post-shock load trace of one deployed configuration, for Table 2 and the stars of Figure 5 |
| `random-sample -uniform-bins 100 <out.csv> <draws> <seed>` | realized-load bin counts per randomly drawn configuration, the simulated side of Figure 5 |
| `kappa-fees -mode defense\|attack -dist <shape> -param <e> -alpha <a>` | the base-fee trajectory of every chain at one point of the Figure 7 or Figure 8 sweep |
| `mempool-check -figure fig4a\|fig4c -points <list>` | the load statistics of named grid cells at a chosen transaction-pool bound |
| `mempool-windows -eps <e> -alpha <a>` | the load statistics of one cell over consecutive block windows, at `Q = 20` beside `Q = 100` |

`boundary-sweep` and `appendix-sweep` write one CSV per scenario into `-output-dir`.
`fig12` is the one that nests, putting its six files under `dmax5`, `dmax7` and
`dmax10`. `mitigation-sweep` writes one CSV per mode. `deployed-chain` and
`random-sample` take their output path as a positional argument, and
`varying-elasticity` takes it as `-output`. `kappa-fees` writes raw little-endian
float64 to stdout, chain 0's whole series first, then chain 1's, then chain 2's.
`mempool-check` and `mempool-windows` print a table to stdout and write no file.

`random-sample` emits the simulator's default census bin edges unless
`-uniform-bins N` replaces them with N equal-width bins over [0,1]. Figure 5
scores its sweep against a mapping on one hundred bins, so it passes
`-uniform-bins 100` and the two contract directly.

`nonuniform-2d` ships more jobs than its `-job` help line lists. The three
that Figure 6 uses are `grid-chain1-125`, `grid-A-chain1-125` and `grid-C-chain1-125`,
15,625 points each. See `main/figure-06-nonuniform-update-rate/README.md`.


## Figure flags

The identifiers in `-figure` and `-mode` are the paper's own numbers. They select the
following grids.

| flag | paper | points per run |
|---|---|---|
| `boundary-sweep -figure fig4a` | Figures 4a and 4b under spike, Figures 11a and 11b under bimodal and uniform | 47,817 |
| `boundary-sweep -figure fig4c` | Figure 4c under spike, Figures 11c and 11d under bimodal and uniform | 37,125 |
| `appendix-sweep -figure fig9-top` | Figures 9a, 9b, 9c | 47,817 |
| `appendix-sweep -figure fig9-bottom` | Figures 9d, 9e, 9f | 47,817 |
| `appendix-sweep -figure fig10` | Figure 10 | 15,939 |
| `appendix-sweep -figure fig12` | Figure 12 | 95,634 |
| `appendix-sweep -figure fig13` | Figure 13 | 47,817 |
| `mitigation-sweep -mode fig4a` | the compensated rerun of the Figure 4a grid, Appendix D | 15,939 |
| `mitigation-sweep -mode fig4c` | the compensated rerun of the Figure 4c grid, drawn as Figure 16a | 12,375 |
| `mitigation-sweep -mode gamma` | Figure 16b, the estimation-error scan | 60,200 |

Every scenario inside a run is its own 15,939-point grid. The exception is `fig4c`,
whose grid is 12,375. That is what multiplies the counts above: `fig4a` walks three
latency shapes, `fig12` walks two shapes at three delay windows, and `fig13` walks
three chain counts. Figure 15 is not a flag of its own. It is four `fig4a` runs at
`-mempool 10`, `20`, `50` and `100`.

Only these spellings are accepted. The internal sweep identifiers `fig6`, `fig7`,
`fig11`, `fig14` and `fig4b` are rejected. Note also that `fig10`, `fig12` and `fig13`
now name the paper's figures of those numbers, which are not the sweeps that once
carried those names.

## Load statistics

Every run is 50,100 blocks long and carries its one-block demand shock at block 100.
`core.StatWarmup` drops those first 100 blocks before the realized-load statistics are
computed, so `avg_load`, `load_std`, `load_inflation` and `full_block_fraction`
describe the 50,000 blocks after the shock, block 100 through block 50,099. Load
inflation is that window's mean load divided by the target, minus one.

Convergence is a separate test on the tail of the trace: every one of the final 50
blocks must sit within 0.1% of the target. It does not depend on the statistics window.

## Determinism

Chains are processed in sorted order at every step and no randomness enters the
sweeps, so a sweep is a pure function of its grid. `random-sample` draws parameters
from a seeded PRNG and is likewise reproducible.

## Options

`-workers` sets the number of concurrent trajectories and defaults to `GOMAXPROCS`.
`boundary-sweep`, `appendix-sweep`, `mitigation-sweep`, `nonuniform-2d` and
`varying-elasticity` carry it. `random-sample` fixes its own pool at one below the
core count. `-output-dir` selects where the CSVs land. `-progress-every` controls the
progress cadence on stderr and does not affect the output.

`-mempool` sets each chain's transaction-pool bound, in multiples of the block gas
limit. It defaults to 20, the value Section 7.1 fixes, and `-mempool 0` restores an
unbounded pool. `-total-steps` sets the horizon in blocks, including the 100 pre-shock
blocks. It defaults to 50,100, which leaves the 50,000 measured blocks.
`boundary-sweep`, `appendix-sweep`, `deployed-chain`, `random-sample` and `kappa-fees`
carry both flags.

The two mempool tools deviate. `mempool-check` spells the horizon `-steps` and treats
`-steps 0` as "keep the sweep default". `mempool-windows` carries `-total-steps` but
not `-mempool`, because it reports `Q = 20` and `Q = 100` side by side on every run.

`mitigation-sweep`, `mitigation-deployed`, `nonuniform-2d` and `varying-elasticity`
carry neither flag. They always run 50,100 blocks with the pool bounded at 20.

## config.yml

`config.yml` is a standalone single-trajectory example, and `bin/simulate` is the only
thing that reads it. It carries `total_steps: 50100` and `mempool_cap: 20`, so a run
from it measures the same 50,000 blocks under the same pool bound as every sweep. It
describes three chains under spike latency at `delta = 0.125`. Editing it changes
nothing else in the artifact. The sweeps build their configurations in code, and the
kappa sweeps of Figures 7 and 8 run through `cmd/kappa-fees`, which does the same.

`bin/simulate` reads the file from the working directory. It writes
`enhanced_simulation_analysis_<timestamp>.log` there, one row every fifth block, and
prints each chain's final base fee.
