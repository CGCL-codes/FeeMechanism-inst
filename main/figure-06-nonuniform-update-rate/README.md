# Figure 6 — the load pattern over the (delta_0, delta_peer) plane

Section 7.4. All other experiments scan the uniform diagonal `delta_i = delta`. This
one lets Chain 0 and the two peers run different update rates, which answers two
questions: whose rate binds a chain's stability boundary, and whether an unstable chain
damages its stable neighbours.

Six panels, three configurations by two views.

| paper | configuration | view | output |
|---|---|---|---|
| Figure 6a | baseline | Chain 0's load | `figures/figure-06a.pdf` |
| Figure 6b | baseline | the larger of the two peers' loads | `figures/figure-06b.pdf` |
| Figure 6c | 20% outbound | Chain 0 | `figures/figure-06c.pdf` |
| Figure 6d | 20% outbound | peers | `figures/figure-06d.pdf` |
| Figure 6e | `lambda_j0 = 16` | Chain 0 | `figures/figure-06e.pdf` |
| Figure 6f | `lambda_j0 = 16` | peers | `figures/figure-06f.pdf` |

Colour is the share of blocks that reach the gas limit, on one scale shared by all six
panels so a colour means the same thing everywhere. The black curve is the exact
boundary `rho(M_ext) = 1` under per-chain update rates, and the pale region inside it
converges.

## Configurations

Three chains, spike latency at `d_max = 5`, destination-side elasticity 16 on every
cross-chain flow, grid `(delta_0, delta_peer)` over `[0.001, 0.125]^2` at step 0.001,
which is 15,625 points per configuration.

| configuration | Chain 0 | each peer | `lambda_j0` |
|---|---|---|---|
| baseline | 20% local, 80% inbound, no outbound | 10% local, 40% outbound to Chain 0, 25% to the other peer | 1.5 |
| 20% outbound | Chain 0's local load converted to 10% outbound per peer | 0% local, absorbing the 10% inbound from Chain 0 | 1.5 |
| `lambda_j0 = 16` | as baseline | as baseline | 16 |

Every off-diagonal destination-side elasticity is 16, so each of the three chains has a
boundary of its own inside the scanned range. Convergence is judged system-wide, so
every chain's load must stay within the 0.1% band over the final 50 blocks.

## Data

| file | configuration |
|---|---|
| `data/baseline_local20.csv` | baseline |
| `data/outbound20.csv` | 20% outbound |
| `data/lambda16.csv` | `lambda_j0 = 16` |

Columns: the three update rates, the perturbation mode, per-chain convergence flags,
per-chain average load, per-chain load inflation and load standard deviation over the
50,000 measured blocks, per-chain full-block fraction, and Chain 0's maximum fee
deviation.

## Reproduce the figure

```bash
python3 plot_inflation_maps.py
```

The script rebuilds the exact boundary from the companion matrix for each configuration
and renders the six panels. Expected output:

```
[scale] colour bar spans 0 to 53% full blocks
[baseline] simulation/M_ext agreement 15625/15625 (100.00%)
[baseline] delta_peer_max = 0.058
[baseline] delta_0_max = 0.022, widening to 0.026
[baseline] max chain-0 full blocks 51.1%, max peer full blocks 51.6%
[baseline] max chain-0 inflation 5.9%, max peer inflation 6.1%
[lambda16] simulation/M_ext agreement 15623/15625 (99.99%)
[lambda16] delta_peer_max = 0.125
[lambda16] delta_0_max = 0.022, widening to 0.061
[lambda16] max chain-0 full blocks 51.1%, max peer full blocks 45.6%
[lambda16] max chain-0 inflation 5.9%, max peer inflation 3.9%
[outbound20] simulation/M_ext agreement 15625/15625 (100.00%)
[outbound20] delta_peer_max = 0.043
[outbound20] delta_0_max = 0.022, widening to 0.029
[outbound20] max chain-0 full blocks 52.0%, max peer full blocks 52.0%
[outbound20] max chain-0 inflation 6.2%, max peer inflation 6.2%
```

The baseline numbers are the paper's. The stable region is a rectangle whose horizontal
edge sits at `delta_peer = 0.058` regardless of `delta_0`, and whose vertical edge sits
at `delta_0 = 0.022`, widening only to 0.026 as the peers approach their own bound. Each
chain's boundary is therefore governed by its own update rate. The simulated verdict and
`rho(M_ext)` agree on all 15,625 baseline configurations and on all 15,625 of the 20%
outbound configurations. Under `lambda_j0 = 16` they differ on two cells out of 15,625,
both within one grid step of the boundary.

## The two bands the section reads

Section 7.4 reads two bands off these grids. The counts below come from the shipped
CSVs, and any of them can be recomputed with a few lines of pandas.

**Peers unstable, Chain 0 inside its own bound** (`delta_peer > 0.058`, `delta_0 <
0.022`, 1,407 cells). In the baseline, Chain 0 converges on only 0.4% of the band, so it
is unstable almost everywhere. Its load oscillates with a standard deviation of up to
0.217 around the target. It still never fills more than 0.16% of its blocks, because its
inbound flows respond to the peers' prices with the weak source-side elasticity 1.5. The
oscillation simply never reaches the gas limit.

**Chain 0 unstable, peers conservative** (`delta_peer <= 0.058`, `delta_0 > 0.026`). The
peers saturate although their own update rates are inside the bound. Up to 49.5% of
their blocks reach the gas limit, with a median of 32.6% over the band, and 30.9% at the
median even at `delta_peer = 0.001`.

The other two configurations isolate the mechanism. Converting Chain 0's local load into
outbound load tightens the peers' bound from 0.058 to 0.043, and over the same band as
the baseline it lifts Chain 0's full-block share from a maximum of 0.16% to a median of
36.8% and a maximum of 48.0%. Raising `lambda_j0` to 16 instead moves the peers' bound
past the top of the scanned grid, and Chain 0 then converges everywhere in the band and
fills no block at all.

## Rerun the sweep

From the artifact root, after `./build.sh`:

```bash
./bin/nonuniform-2d -job grid-chain1-125    -output-dir main/figure-06-nonuniform-update-rate/data
./bin/nonuniform-2d -job grid-A-chain1-125  -output-dir main/figure-06-nonuniform-update-rate/data
./bin/nonuniform-2d -job grid-C-chain1-125  -output-dir main/figure-06-nonuniform-update-rate/data
```

These write `nonuniform_grid_chain1_125.csv`, `nonuniform_grid_A_local20_125.csv` and
`nonuniform_grid_C_lambda16_125.csv`, which correspond to `outbound20.csv`,
`baseline_local20.csv` and `lambda16.csv` respectively. Each job evaluates 15,625
trajectories.
