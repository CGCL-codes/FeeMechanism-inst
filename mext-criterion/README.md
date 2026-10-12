# Exact stability criterion

`mext_criterion.py` computes the exact local stability verdict for a configuration
by building the augmented companion matrix `M_ext` of the governing recurrence and
testing whether its spectral radius is below one.

The multi-chain recurrence couples `N` chains across a delay window of `d_max` steps.
Stacking the delayed states gives a linear system `X(t+1) = M_ext X(t)` of dimension
`N(d_max + 1)`. The system is locally asymptotically stable if and only if
`rho(M_ext) < 1`. The matrix is assembled from the four channel coefficients of Table 1:
the instantaneous self-feedback, the instantaneous peer feedback, the delayed
self-feedback and the delayed peer feedback.

The script reconstructs each experiment's parameters from the CSV rows themselves
rather than from any configuration file left behind by a simulation run, so a result
file is self-describing.

## Use

```bash
python3 mext_criterion.py <experiment> <csv> [<csv> ...] (--in-place | --output-dir DIR)
```

`<experiment>` is one of `fig4a`, `fig4c`, `fig9-top`, `fig9-bottom`, `fig10`, `fig12`
and `fig13`. These are the paper's figure numbers, and they are the only spellings the
script accepts. Each one fixes the swept parameter, the coupling direction, the delay
window and the chain count that the rows are read under.

| experiment | CSVs it annotates |
|---|---|
| `fig4a` | `main/figure-04-stability-boundary/data/convergence_results_Spike.csv`, the two shapes under `appendix/figure-11-latency-shapes/`, the four capacities under `appendix/figure-15-mempool-sensitivity/` |
| `fig4c` | `main/figure-04-stability-boundary/data/convergence_results_delta_Spike.csv`, the two `delta` shapes under `appendix/figure-11-latency-shapes/`, the three shapes under `appendix/figure-14-varying-elasticity-boundary/` |
| `fig9-top` | `appendix/figure-09-attack-channels/data/delayed-channel/` |
| `fig9-bottom` | `appendix/figure-09-attack-channels/data/instantaneous-channel/` |
| `fig10` | `appendix/figure-10-instantaneous-channel-dmax1/data/` |
| `fig12` | `appendix/figure-12-varying-dmax/data/dmax5`, `dmax7` and `dmax10` |
| `fig13` | `appendix/figure-13-varying-chain-count/data/` |

Three columns are appended to each row.

| column | meaning |
|---|---|
| `mext_rho` | the spectral radius of `M_ext` |
| `mext_stable` | whether `mext_rho < 1` |
| `classification_match` | whether the exact verdict agrees with the simulated one |

The command prints the agreement rate per file. Running it on the shipped Figure 4a
file reprints `15938/15939 classifications agree (99.994%)`, and the Figure 4c file
reprints `12375/12375 (100.000%)`.

## Options

`--max-delay` is required for `fig12`, whose delay window is not recoverable from the
rows. Pass the same value as the directory the file came from, so `--max-delay 7` for
`data/dmax7`. `--num-shards` overrides the chain count, which `fig13` otherwise reads
per row from its `num_shards` column.

## The compensated criterion

`mext_compensated.py` does the same for the compensated controller of Appendix D. The
gain `H_i` enters as a diagonal `K = diag(H_i)`, which is added to the instantaneous
block and subtracted from every delayed block. Setting every `H_i` to zero recovers
the `M_ext` of the main text, so the two scripts agree on the plain controller.

```bash
python3 mext_compensated.py <mode> <csv> [<csv> ...] --in-place
```

`--in-place` is required. There is no `--output-dir`.

| mode | reads | rebuilds each row at |
|---|---|---|
| `fig4a` | `appendix/figure-16-mitigation/data/mitigation_fig4a_Spike.csv` | the row's `epsilon_j0`, `delta = 0.125`, spike `d_max = 5` |
| `fig4c` | `appendix/figure-16-mitigation/data/mitigation_fig4c_Spike.csv` | elasticity 16, the row's `delta`, spike `d_max = 5` |
| `gamma` | `appendix/figure-16-mitigation/data/mitigation_gamma_Spike.csv` | elasticity 16, the row's `delta`, spike `d_max = 5` |
| `deployed` | `appendix/table-03-deployed-compensation/data/mitigation_deployed_Spike.csv` | elasticity 16, the row's `delta`, spike at the row's `d_max` |

Every mode reads the row's own `gamma` and sets `H_i = gamma * Lambda_i^delay`, so
`gamma = 0` is plain EIP-1559 and `gamma = 1` is exact compensation. `deployed` is the
only mode that takes the delay window from the rows, which is what lets Cosmos Hub at
`d_max = 10` and Osmosis at `d_max = 25` share one file. It appends the same three
columns as `mext_criterion.py`.

On the shipped files the four modes report `15939/15939`, `12375/12375`,
`60195/60200 (99.992%)` and `602/602`.

## What ships annotated

Every CSV that either script covers is shipped with the three columns already in
place. That is 33 files and 529,963 rows, and it includes the three Figure 16 files
and the 602 rows of
`appendix/table-03-deployed-compensation/data/mitigation_deployed_Spike.csv`, whose
verdicts all agree. Re-annotating any of them is idempotent. For the Table 3 file the
command is

```bash
python3 mext-criterion/mext_compensated.py deployed \
  appendix/table-03-deployed-compensation/data/mitigation_deployed_Spike.csv --in-place
```

Figure 6 is outside both scripts. Its rows carry a per-chain update rate, and
`main/figure-06-nonuniform-update-rate/plot_inflation_maps.py` builds that boundary
itself.

## Why both criteria

The exact criterion returns a binary verdict for a configuration but says nothing about
the magnitude of the resulting load inflation, which is what the security analysis
needs. The nonlinear simulation supplies the magnitude but classifies over a finite
50,000-block horizon, so it can misclassify slowly converging or slowly diverging
trajectories. The figures report both.

The disagreements crowd `rho = 1`. Across every annotated CSV in the artifact
they number 2,036 rows out of 529,963, and their `mext_rho` values span
`[0.999989, 1.048666]`. In 2,028 of them the simulation converged while `rho >= 1`, and
in the remaining 8 it did not converge while `rho < 1`. The single disagreement on the
Figure 4a grid is one of those 8, at `rho(M_ext) = 0.999993`.
