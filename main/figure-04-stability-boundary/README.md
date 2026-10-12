# Figure 4 — Pathway 1 under spike latency

Section 7.2. Three views of the same three-chain system under spike latency
(`d_max = 5`, all delay mass at slot 5), all produced by one script.

| paper | output |
|---|---|
| Figure 4a | `figures/over-correction-bubble-chart-spike.pdf` |
| Figure 4b | `figures/over-correction-load-pattern-spike.pdf` |
| Figure 4c | `figures/over-correction-bubble-chart-delta-spike.pdf` |

Figure 4a is the stable region over the destination-side elasticity `epsilon_j0` and the
inbound ratio `sum alpha_{j->0,in}`, at the fixed Ethereum update rate `delta = 0.125`.
Figure 4c is `Delta_safe` over the update rate `delta` and the inbound ratio, at the
fixed elasticity 16. On both maps, bubble size encodes the realized-load standard
deviation and bubble colour encodes the share of blocks that reach the gas limit. The
solid line is the simulated boundary and the dashed line is the exact boundary
`rho(M_ext) = 1`.

Figure 4b takes the unstable cells of Figure 4a and plots their load inflation against
`rho(M_ext)`, the spectral radius that decides stability. Colour again carries the
share of full blocks. The dashed line is the inflation bound
`-ln(1 - delta^2) / ln((1 + delta)/(1 - delta)) = 6.27%` at `delta = 0.125`, which the
mechanism obeys for any demand. The bracket encloses the cells that never fill a block,
and the script traces it from the data rather than drawing it by hand.

Statistics are measured over the 50,000 blocks after the shock, so block 100 to block
50,099 of the 50,100-block run. Each chain has a transaction pool bounded at 20 block
gas limits.

The same sweep also produces the bimodal and uniform panels of Figure 11. Those live in
`appendix/figure-11-latency-shapes/`.

## Data

| file | grid |
|---|---|
| `data/convergence_results_Spike.csv` | `epsilon_j0` from 16.0 down to 0.0 at step 0.1, `alpha` from 0.99 down to 0.01 at step 0.01 (15,939 rows) |
| `data/convergence_results_delta_Spike.csv` | `delta` from 0.125 down to 0.001 at step 0.001, same `alpha` grid (12,375 rows) |

Columns: the swept parameter, `alpha_inflow`, `distribution`, `final_load`, `avg_load`,
`load_std`, `load_inflation`, `converged`, `full_block_fraction`, and the three
exact-criterion columns `mext_rho`, `mext_stable`, `classification_match`.

## Reproduce the figure

```bash
python3 plot_figure4.py
```

Expected output:

```
[OK] figures/over-correction-bubble-chart-spike.pdf
     8008 unstable cells, full-block share up to 52.74%, inflation up to 6.2568%
     simulation/M_ext agreement: 15938/15939 (99.994%)
[OK] figures/over-correction-load-pattern-spike.pdf
     rho in [1.0000, 1.2767], 1314 unstable cells never fill a block
     unsaturated region reaches rho = 1.0634 and inflation = 2.070%
[OK] figures/over-correction-bubble-chart-delta-spike.pdf
     6806 unstable cells, full-block share up to 52.45%, inflation up to 6.2149%
     simulation/M_ext agreement: 12375/12375 (100.000%)
```

These are the paper's headline numbers. On the Figure 4a grid the simulated verdict
matches `rho(M_ext) < 1` on 15,938 of the 15,939 configurations, a 99.994% agreement.
The single disagreement sits at `rho(M_ext) = 0.999993`, close enough to the boundary
that the 50,000-block convergence test cannot resolve it. The Figure 4c grid agrees on
all 12,375 configurations.

Instability does not require full blocks. Of the 8,008 unstable cells in Figure 4a,
1,314 never fill a single block, which is 16.4% of them, and those cells still inflate
load by up to 2.070%. Across the whole unstable region the share of full blocks reaches
52.74% and load inflation reaches 6.2568%, against the 6.27% bound. Maximum stable
elasticity drops from the monolithic 16 to 3.1 at `alpha = 0.97`.

Figure 4c reads the same collapse through the update rate. At an inbound ratio of 0.99
the largest converging `delta` is 0.018 and every `delta` from 0.019 upward diverges, so
`Delta_safe` collapses to `delta < 0.019`. That is an 84.8% erosion relative to the
monolithic bound 0.125.

## Rerun the sweep

From the artifact root, after `./build.sh`:

```bash
./bin/boundary-sweep -figure fig4a -mempool 20 -total-steps 50100 -output-dir main/figure-04-stability-boundary/data
./bin/boundary-sweep -figure fig4c -mempool 20 -total-steps 50100 -output-dir main/figure-04-stability-boundary/data
python3 mext-criterion/mext_criterion.py fig4a main/figure-04-stability-boundary/data/convergence_results_Spike.csv --in-place
python3 mext-criterion/mext_criterion.py fig4c main/figure-04-stability-boundary/data/convergence_results_delta_Spike.csv --in-place
```

`-mempool` and `-total-steps` carry the defaults shown above, so they may be omitted.
Setting `-mempool 0` restores an unbounded transaction pool.

Each `boundary-sweep` invocation writes all three latency distributions, so `fig4a`
covers 47,817 points and `fig4c` covers 37,125. Move the Uniform and Bimodal files to
`appendix/figure-11-latency-shapes/data/` and annotate them the same way.

Each `mext_criterion.py` run reprints the agreement counts quoted above.
