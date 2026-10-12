# Figure 14 — the stability boundary under a price-dependent elasticity

Appendix B.3. The Figure 4c sweep rerun with the inbound elasticity
`epsilon_{j->0}` a function of Chain 0's own normalized base fee `x` rather
than a constant. Three shapes are evaluated, each truncated below at zero and
each passing through 16 at the equilibrium price `x = 1`:

```
log       eps(x) = max(0, 16 + ln x)
linear    eps(x) = min(16x, 32)
logistic  eps(x) = 32 x^2 / (x^2 + 1)
```

Everything else is the Figure 4c protocol: inbound-coupled topology, spike
latency with `d_max = 5`, `delta` 0.001 to 0.125 at step 0.001, `alpha_in` 0.01
to 0.99 at step 0.01, one-block 1.01x shock, 50,100 steps, transaction pool
bounded at 20x the block gas limit.

| paper | script | output |
|---|---|---|
| Figure 14a | `plot_delta_safe_shapes.py` | `figures/varying-elasticity-boundary-log.pdf` |
| Figure 14b | `plot_delta_safe_shapes.py` | `figures/varying-elasticity-boundary-linear.pdf` |
| Figure 14c | `plot_delta_safe_shapes.py` | `figures/varying-elasticity-boundary-logistic.pdf` |

The three panels are drawn by `figure-style/boundary_panel.py`, so they carry
the Figure 4a contract. Bubble colour is the share of blocks that reach the gas
limit, and each panel's colour bar is topped at the largest share that panel
itself reaches.

## Data

| shape | file | `Delta_safe` | M_ext agreement | unstable | max % full | never full | elasticity visited |
|---|---|---|---|---|---|---|---|
| log | `data/convergence_results_delta_log_Spike.csv` | 0.019 | 12,375/12,375 | 6,806 | 52.45% | 1,114 | [15.352, 21.067] |
| linear | `data/convergence_results_delta_linear_Spike.csv` | 0.019 | 12,375/12,375 | 6,806 | 52.73% | 1,198 | [8.300, 32.000] |
| logistic | `data/convergence_results_delta_logistic_Spike.csv` | 0.019 | 12,374/12,375 | 6,805 | 52.72% | 1,208 | [6.785, 31.999] |

Each grid is 125 update rates against 99 inbound ratios, so 12,375 rows.
Columns: `delta`, `alpha_inflow`, `distribution`, `final_load`, `avg_load`,
`load_std`, `load_inflation`, `converged`, `full_block_fraction`, `eps_min`,
`eps_max`, and the three exact-criterion columns `mext_rho`, `mext_stable`,
`classification_match`. `eps_min` and `eps_max` record the elasticity range the
shape presented along that cell's trajectory, and the last column of the table
is their extent over the whole grid.

The headline check is that the boundary does not move. Every shape gives
`Delta_safe = [0, 0.019)`, an 84.8% shrinkage from the monolithic 0.125, and
the largest converging `delta` at an inbound ratio of 0.99 is 0.018 in all
three. The log and linear runs mark exactly the same 6,806 cells unstable as
the constant-elasticity grid in
`main/figure-04-stability-boundary/data/convergence_results_delta_Spike.csv`.
The logistic run converges at one further cell, `delta = 0.115` and
`alpha_in = 0.20`, where `rho(M_ext) = 1.000015` sits just above one. That cell
is the only simulation-against-`M_ext` disagreement in the three files.

The exact criterion explains the agreement. At the equilibrium the shape's
slope enters the linearisation only through a factor `ln(1) = 0`, so `M_ext`
reads the shape at `eps(1) = 16` alone. The `mext_rho` column is therefore
identical across the three files and identical to the constant-elasticity grid,
cell for cell.

Severity barely separates the shapes. The largest full-block share is
52.45%, 52.73% and 52.72%, and the largest load inflation is 6.2141%, 6.2330%
and 6.2357%, all under the 6.27% bound of Section 7.2. What the shapes do
separate is the elasticity a trajectory actually visits. The log shape stays
within [15.352, 21.067] and never leaves the neighbourhood of the anchor 16.
The linear and logistic shapes both reach the ceiling of 32 and fall to 8.300
and 6.785. That difference shows up in how many unstable cells stay off the gas
limit entirely: 1,114 under log, 1,198 under linear and 1,208 under logistic.

## Reproduce the figure

Run from this directory:

```bash
python3 plot_delta_safe_shapes.py
```

Expected output:

```
[OK] Loaded data/convergence_results_delta_log_Spike.csv: 12375 records

Spike (log)
  M_ext rho range: 0.813438 - 1.276725
  Load std range: 0.000000 - 0.496317
  Elasticity range along the trajectories: 15.352 - 21.067
  Full-block share range over unstable cells: 0 - 52.45%
  Unstable cells that never fill a block: 1114
  Delta_safe: [0, 0.019); shrinkage: 84.8%
[OK] figures/varying-elasticity-boundary-log.pdf
     6806 unstable cells, full-block share up to 52.45%, inflation up to 6.2141%
     simulation/M_ext agreement: 12375/12375 (100.000%)
[OK] Loaded data/convergence_results_delta_linear_Spike.csv: 12375 records

Spike (linear)
  M_ext rho range: 0.813438 - 1.276725
  Load std range: 0.000000 - 0.496949
  Elasticity range along the trajectories: 8.300 - 32.000
  Full-block share range over unstable cells: 0 - 52.73%
  Unstable cells that never fill a block: 1198
  Delta_safe: [0, 0.019); shrinkage: 84.8%
[OK] figures/varying-elasticity-boundary-linear.pdf
     6806 unstable cells, full-block share up to 52.73%, inflation up to 6.2330%
     simulation/M_ext agreement: 12375/12375 (100.000%)
[OK] Loaded data/convergence_results_delta_logistic_Spike.csv: 12375 records

Spike (logistic)
  M_ext rho range: 0.813438 - 1.276725
  Load std range: 0.000000 - 0.496964
  Elasticity range along the trajectories: 6.785 - 31.999
  Full-block share range over unstable cells: 0 - 52.72%
  Unstable cells that never fill a block: 1208
  Delta_safe: [0, 0.019); shrinkage: 84.8%
[OK] figures/varying-elasticity-boundary-logistic.pdf
     6805 unstable cells, full-block share up to 52.72%, inflation up to 6.2357%
     simulation/M_ext agreement: 12374/12375 (99.992%)
```

## Rerun the sweeps

From the artifact root, after `./build.sh`:

```bash
./bin/varying-elasticity -shape log      -output appendix/figure-14-varying-elasticity-boundary/data/convergence_results_delta_log_Spike.csv
./bin/varying-elasticity -shape linear   -output appendix/figure-14-varying-elasticity-boundary/data/convergence_results_delta_linear_Spike.csv
./bin/varying-elasticity -shape logistic -output appendix/figure-14-varying-elasticity-boundary/data/convergence_results_delta_logistic_Spike.csv
python3 mext-criterion/mext_criterion.py fig4c appendix/figure-14-varying-elasticity-boundary/data/convergence_results_delta_log_Spike.csv --in-place
python3 mext-criterion/mext_criterion.py fig4c appendix/figure-14-varying-elasticity-boundary/data/convergence_results_delta_linear_Spike.csv --in-place
python3 mext-criterion/mext_criterion.py fig4c appendix/figure-14-varying-elasticity-boundary/data/convergence_results_delta_logistic_Spike.csv --in-place
```

Each grid evaluates 12,375 trajectories and takes about two minutes on ten
workers. Each grid prints its `delta_safe` and its largest load inflation over
the whole grid on completion, `delta_safe=0.019 max_inflation=0.0621` for the
log shape. The criterion mode is `fig4c`, the plain Figure 4c mode, because the
exact criterion of every shape is the constant-elasticity criterion at
`eps(1) = 16`. Each criterion run reprints the agreement count of the table
above, for instance `12374/12375 classifications agree (99.992%)` for the
logistic file.
