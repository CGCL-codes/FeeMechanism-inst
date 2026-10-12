# Figure 15 — the stable region against the transaction-pool bound

Appendix B.4. Section 7.1 gives each chain a pool of `Q = 20` block gas limits.
The capacity belongs to a client implementation rather than to the fee
mechanism, so the Figure 4a scan is rerun at `Q` in {10, 20, 50, 100} with the
grid, the shock, the latency shape and the convergence test of Section 7.2 left
untouched.

Everything else is the Figure 4a protocol: inbound-coupled topology, spike
latency with `d_max = 5`, `delta = 0.125`, `epsilon_j0` 0 to 16 at step 0.1,
`alpha_in` 0.01 to 0.99 at step 0.01, one-block 1.01x shock, 50,100 steps.

| paper | script | output |
|---|---|---|
| Figure 15a | `plot_mempool_panels.py` | `figures/over-correction-bubble-chart-spike-q10.pdf` |
| Figure 15b | `plot_mempool_panels.py` | `figures/over-correction-bubble-chart-spike-q20.pdf` |
| Figure 15c | `plot_mempool_panels.py` | `figures/over-correction-bubble-chart-spike-q50.pdf` |
| Figure 15d | `plot_mempool_panels.py` | `figures/over-correction-bubble-chart-spike-q100.pdf` |

Panel 15b is the `Q = 20` setting of the main body. Its data file reproduces
`main/figure-04-stability-boundary/data/convergence_results_Spike.csv`.

Each panel carries its own colour scale, topped at the largest share of full
blocks that the panel itself reaches, so the drift in that share is what the
four panels show.

## Data

| file | `Q` | unstable | max % full | max inflation | never full | M_ext agreement |
|---|---|---|---|---|---|---|
| `data/convergence_results_Spike_q10.csv` | 10 | 8,008 | 51.86% | 6.1226% | 1,314 | 15,938/15,939 |
| `data/convergence_results_Spike_q20.csv` | 20 | 8,008 | 52.74% | 6.2568% | 1,314 | 15,938/15,939 |
| `data/convergence_results_Spike_q50.csv` | 50 | 8,008 | 52.99% | 6.4112% | 1,314 | 15,938/15,939 |
| `data/convergence_results_Spike_q100.csv` | 100 | 8,008 | 53.15% | 6.5959% | 1,314 | 15,938/15,939 |

Columns are those of Figure 4a: `epsilon_j0`, `alpha_inflow`, `distribution`,
`final_load`, `avg_load`, `load_std`, `load_inflation`, `converged`,
`full_block_fraction`, and the three exact-criterion columns.

All four runs mark the same 8,008 cells unstable and no cell changes verdict,
so the boundary does not move. The one cell on which the simulation and
`rho(M_ext)` disagree is the same cell in every run. Between `Q = 10` and
`Q = 100`, 4,789 of the 8,008 unstable cells report exactly the same full-block
share (59.8%), and the largest change is 5.15 percentage points.

`data/inflation_windows_eps9.8_alpha0.99.txt` follows the most saturated cell of
the grid, `epsilon_j0 = 9.8` and `alpha_in = 0.99`, over consecutive
25,000-block windows out to 5,000,100 blocks at `Q = 20` and `Q = 100`. It backs
the last paragraph of Appendix B.4:

| reading | `Q = 20` | `Q = 100` |
|---|---|---|
| first 25,000 blocks | 6.1960% | 6.7641% |
| largest 25,000-block window after block 50,000, within the first 500,000 | 6.2138% | 6.4421% |
| largest such window over the whole 5,000,000 | 6.2138% | 6.4484% |
| average over 500,000 blocks | 6.1350% | 6.2442% |
| average over 5,000,000 blocks | 6.1296% | 6.2317% |

`Q = 100` runs above its long-run level for as long as the pool is filling, and
`Q = 20` shows no such transient.

## Reproduce the figure

```bash
python3 plot_mempool_panels.py
```

Each panel prints its unstable count, its full-block ceiling and its `M_ext`
agreement, then the script prints the cross-capacity comparison above.

## Rerun the sweeps

From the artifact root, after `./build.sh`:

```bash
DIR=appendix/figure-15-mempool-sensitivity
for q in 10 20 50 100; do
  ./bin/boundary-sweep -figure fig4a -mempool $q -output-dir $DIR/data/q$q
  mv $DIR/data/q$q/convergence_results_Spike.csv $DIR/data/convergence_results_Spike_q$q.csv
  rm -r $DIR/data/q$q
  python3 mext-criterion/mext_criterion.py fig4a \
    $DIR/data/convergence_results_Spike_q$q.csv --in-place
done
```

`boundary-sweep` walks all three latency shapes and writes one CSV each. Only
the spike file is used here, so each pass costs the full Figure 4a sweep and the
Uniform and Bimodal outputs are discarded. `-figure fig4a` is the Figure 4a grid,
described in `main/figure-04-stability-boundary/README.md`.

The window scan is one cell and takes seconds:

```bash
./bin/mempool-windows -eps 9.8 -alpha 0.99 -total-steps 5000100 -segment 25000 \
  > appendix/figure-15-mempool-sensitivity/data/inflation_windows_eps9.8_alpha0.99.txt
```
