# Figure 13 — Stability boundary with 5, 7 and 10 chains

Appendix B.2. All other experiments use three chains. This one expands the system to
test whether network scale drives the instability.

| panel | output |
|---|---|
| 13a | `figures/over-correction-bubble-chart-5.pdf` |
| 13b | `figures/over-correction-bubble-chart-7.pdf` |
| 13c | `figures/over-correction-bubble-chart-10.pdf` |

Spike latency at `d_max = 5`, the most severe shape tested. Chain 0's inbound share is
split equally across the other chains.

The boundary is nearly invariant to the chain count. The critical elasticity, the
smallest `epsilon_j0` at which any inbound ratio fails to converge, is 3.0 with 5 chains,
2.8 with 7 and 2.7 with 10. Those are contractions of 81.3%, 82.5% and 83.1% from the
monolithic boundary of 16. Doubling the network from five chains to ten moves the boundary by 0.3 in
elasticity.

Saturation is flat as well. The worst full-block share is 52.74% at every chain count,
and the count of unstable cells grows only from 8,179 to 8,265 to 8,335 out of 15,939.
Delay and coupling strength, not the number of chains, govern instability over the
tested range.

## Data

`data/convergence_results_spike_shard{5,7,10}.csv`, 15,939 points each. The grid is
`epsilon_j0` from 16.0 down to 0.0 at step 0.1 against `alpha_inflow` from 0.99 down to
0.01 at step 0.01. Each row carries its own `num_shards`.

## Reproduce the figure

```bash
python3 plot_boundary.py --figure fig13 --input-dir data --output-dir figures
```

Expected output:

```
[OK] figures/over-correction-bubble-chart-5.pdf
     8179 unstable cells, full-block share up to 52.74%, inflation up to 6.2615%
     simulation/M_ext agreement: 15938/15939 (99.994%)
[OK] figures/over-correction-bubble-chart-7.pdf
     8265 unstable cells, full-block share up to 52.74%, inflation up to 6.2629%
     simulation/M_ext agreement: 15939/15939 (100.000%)
[OK] figures/over-correction-bubble-chart-10.pdf
     8335 unstable cells, full-block share up to 52.74%, inflation up to 6.2626%
     simulation/M_ext agreement: 15938/15939 (99.994%)
```

Add `--summary-json figures/summary.json` to store the per-panel summary, which carries
the critical elasticity as `minimum_unstable_parameter` and the contraction as
`boundary_reduction_from_16`.

## Rerun the sweep

From the artifact root, after `./build.sh`:

```bash
./bin/appendix-sweep -figure fig13 -output-dir appendix/figure-13-varying-chain-count/data
python3 mext-criterion/mext_criterion.py fig13 appendix/figure-13-varying-chain-count/data/*.csv --in-place
```

`mext_criterion.py` reads the chain count from each row for `fig13`, so it needs no
`--num-shards` override.
