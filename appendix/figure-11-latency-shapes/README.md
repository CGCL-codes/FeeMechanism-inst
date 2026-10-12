# Figure 11 — Over-correction under bimodal and uniform latency

Appendix B.2. Figure 4 fixes spike latency, which concentrates the whole delay mass at
one lag. This figure repeats both of its panels under the two dispersed shapes,
bimodal `[0.4, 0, 0.2, 0, 0.4]` and uniform `[0.2, 0.2, 0.2, 0.2, 0.2]`.

| panel | script | output |
|---|---|---|
| 11a | `plot_stable_region.py` | `figures/over-correction-bubble-chart-bimodal.pdf` |
| 11b | `plot_stable_region.py` | `figures/over-correction-bubble-chart-uniform.pdf` |
| 11c | `plot_delta_safe.py` | `figures/over-correction-bubble-chart-delta-bimodal.pdf` |
| 11d | `plot_delta_safe.py` | `figures/over-correction-bubble-chart-delta-uniform.pdf` |

Both shapes preserve the boundary contraction but weaken it. At a 97% inbound ratio the
maximum stable elasticity drops from the monolithic 16 to 6.8 under bimodal latency and
to 5.5 under uniform latency, against 3.1 under spike latency. The top row fails on
3,405 of its 15,939 configurations under bimodal latency and on 4,644 under uniform,
against 8,008 under spike.

The dispersed shapes still drive blocks to the gas limit. The worst full-block share is
46.76% under bimodal latency and 50.29% under uniform, against 52.74% under spike. That
share is what the colour bar carries, and it is measured over the unstable cells of each
panel.

The bottom row erodes `Delta_safe` the same way. It collapses to `delta < 0.044` under
bimodal latency and to `delta < 0.037` under uniform, erosions of 64.8% and 70.4% from
the monolithic 0.125. Under spike latency the collapse is to `delta < 0.019`, an 84.8%
erosion. The ordering matches the `kappa_def` analysis of Appendix B.1. Concentrating a
past deviation into a single step produces the strongest amplification.

The spike figures above are the same quantities read off Figure 4's own CSVs in
`main/figure-04-stability-boundary/data/`, which the sweep here emits in the same run.

## Data and scripts

Same sweep as `main/figure-04-stability-boundary/`, which emits all three latency
shapes in one run. The Uniform and Bimodal CSVs live here and the Spike CSVs live
there.

```bash
python3 plot_stable_region.py
python3 plot_delta_safe.py
```

Each script plots whichever distributions it finds under `data/`. Pass
`--distributions Uniform` to restrict it.

Expected output from `plot_stable_region.py`:

```
[OK] Loaded data/convergence_results_Uniform.csv: 15939 records
[OK] Loaded data/convergence_results_Bimodal.csv: 15939 records

Uniform distribution
  M_ext rho range: 0.813437 - 1.209709
  Load std range: 0.000000 - 0.488576
  Full-block share range over unstable cells: 0 - 50.29%
  Unstable cells that never fill a block: 1746
  Max stable epsilon_j0 at alpha=0.97: 5.5
[OK] figures/over-correction-bubble-chart-uniform.pdf
     4644 unstable cells, full-block share up to 50.29%, inflation up to 6.0689%
     simulation/M_ext agreement: 15939/15939 (100.000%)

Bimodal distribution
  M_ext rho range: 0.813437 - 1.110702
  Load std range: 0.000000 - 0.476915
  Full-block share range over unstable cells: 0 - 46.76%
  Unstable cells that never fill a block: 2039
  Max stable epsilon_j0 at alpha=0.97: 6.8
[OK] figures/over-correction-bubble-chart-bimodal.pdf
     3405 unstable cells, full-block share up to 46.76%, inflation up to 5.7254%
     simulation/M_ext agreement: 15939/15939 (100.000%)
```

Expected output from `plot_delta_safe.py`:

```
[OK] Loaded data/convergence_results_delta_Uniform.csv: 12375 records
[OK] Loaded data/convergence_results_delta_Bimodal.csv: 12375 records

Uniform distribution
  M_ext rho range: 0.813438 - 1.209709
  Load std range: 0.000000 - 0.488576
  Full-block share range over unstable cells: 0 - 50.29%
  Unstable cells that never fill a block: 1490
  Delta_safe: [0, 0.037); shrinkage: 70.4%
[OK] figures/over-correction-bubble-chart-delta-uniform.pdf
     4051 unstable cells, full-block share up to 50.29%, inflation up to 6.0689%
     simulation/M_ext agreement: 12375/12375 (100.000%)

Bimodal distribution
  M_ext rho range: 0.813438 - 1.110702
  Load std range: 0.000000 - 0.475636
  Full-block share range over unstable cells: 0 - 46.96%
  Unstable cells that never fill a block: 1889
  Delta_safe: [0, 0.044); shrinkage: 64.8%
[OK] figures/over-correction-bubble-chart-delta-bimodal.pdf
     3141 unstable cells, full-block share up to 46.96%, inflation up to 5.7080%
     simulation/M_ext agreement: 12374/12375 (99.992%)
```

The bimodal bottom-row share, 46.96%, is not the top row's 46.76%. The two grids sweep
different parameters. The top row sweeps `epsilon_j0` at `delta = 0.125` and the bottom
row sweeps `delta` at elasticity 16, so the worst cell is not the same cell. The
headline shares quoted above are the top row's, which is the row Appendix B.2 reports.

## Rerun the sweep

From the artifact root, after `./build.sh`:

```bash
./bin/boundary-sweep -figure fig4a -output-dir appendix/figure-11-latency-shapes/data
./bin/boundary-sweep -figure fig4c -output-dir appendix/figure-11-latency-shapes/data
python3 mext-criterion/mext_criterion.py fig4a \
    appendix/figure-11-latency-shapes/data/convergence_results_Uniform.csv \
    appendix/figure-11-latency-shapes/data/convergence_results_Bimodal.csv --in-place
python3 mext-criterion/mext_criterion.py fig4c \
    appendix/figure-11-latency-shapes/data/convergence_results_delta_Uniform.csv \
    appendix/figure-11-latency-shapes/data/convergence_results_delta_Bimodal.csv --in-place
```

Each `boundary-sweep` invocation writes all three latency shapes. `fig4a` writes
`convergence_results_{Spike,Uniform,Bimodal}.csv` and `fig4c` writes the matching
`convergence_results_delta_*.csv`. The two Spike files belong to Figure 4, so move them
to `main/figure-04-stability-boundary/data/` and annotate them there.

`-mempool` and `-total-steps` carry the protocol defaults, 20 block gas limits of
transaction pool and a 50,100-block run whose first 100 blocks precede the shock, so
they may be omitted.
