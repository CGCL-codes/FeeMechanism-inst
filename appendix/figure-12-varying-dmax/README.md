# Figure 12 — Stability boundary at d_max = 7 and 10

Appendix B.2. Figure 4 fixes `d_max = 5`. This experiment repeats the fixed-delta sweep
at longer cross-chain latencies to test whether stability degrades with delay.

| panel | output |
|---|---|
| 12a | `figures/latency7-over-correction-bubble-chart-uniform.pdf` |
| 12b | `figures/latency7-over-correction-bubble-chart-spike.pdf` |
| 12c | `figures/latency10-over-correction-bubble-chart-uniform.pdf` |
| 12d | `figures/latency10-over-correction-bubble-chart-spike.pdf` |

The run also writes two `latency5-` panels. Those are the `d_max = 5` baseline, which the
paper shows as Figure 4a rather than as a panel of Figure 12. They are reproduced here
for comparison and are not part of the figure.

Stability degrades monotonically with `d_max`. The critical elasticity is the smallest
`epsilon_j0` at which any inbound ratio fails to converge. Under spike latency it falls
from 3.1 at `d_max = 5` to 2.6 at 7 and 2.4 at 10. At `d_max = 10` that first
non-convergence covers inbound ratios of 92% to 99%, a contiguous band of eight inbound ratios.
An elasticity of 2.4 is an 85.0% contraction from the monolithic boundary of 16. Under
uniform latency the critical elasticities are 5.5, 4.9 and 4.5, contractions of 65.6%,
69.4% and 71.9%.

The worst full-block share barely moves with delay. Under spike latency it is 52.74% at
`d_max = 5`, 52.53% at 7 and 52.26% at 10. Under uniform latency it is 50.29%, 51.08%
and 49.95%. The count of unstable cells does move, from 8,008 to 8,918 to 9,678 under
spike latency and from 4,644 to 5,266 to 5,683 under uniform. Longer delay widens the
unstable region rather than deepening the saturation inside it.

## Data

`data/dmax{5,7,10}/convergence_results_{Spike,Uniform}.csv`, 15,939 points each. The
grid is `epsilon_j0` from 16.0 down to 0.0 at step 0.1 against `alpha_inflow` from 0.99
down to 0.01 at step 0.01.

The `dmax5` grids are the `d_max = 5` baseline of Figure 4a. They are shipped because
one `appendix-sweep` run produces all six grids and the plotting script renders all
three latencies as one figure family.

## Reproduce the figure

```bash
python3 plot_boundary.py --figure fig12 --input-dir data --output-dir figures
```

Expected output:

```
[OK] figures/latency5-over-correction-bubble-chart-uniform.pdf
     4644 unstable cells, full-block share up to 50.29%, inflation up to 6.0689%
     simulation/M_ext agreement: 15939/15939 (100.000%)
[OK] figures/latency5-over-correction-bubble-chart-spike.pdf
     8008 unstable cells, full-block share up to 52.74%, inflation up to 6.2568%
     simulation/M_ext agreement: 15938/15939 (99.994%)
[OK] figures/latency7-over-correction-bubble-chart-uniform.pdf
     5266 unstable cells, full-block share up to 51.08%, inflation up to 6.1179%
     simulation/M_ext agreement: 15938/15939 (99.994%)
[OK] figures/latency7-over-correction-bubble-chart-spike.pdf
     8918 unstable cells, full-block share up to 52.53%, inflation up to 6.2415%
     simulation/M_ext agreement: 15939/15939 (100.000%)
[OK] figures/latency10-over-correction-bubble-chart-uniform.pdf
     5683 unstable cells, full-block share up to 49.95%, inflation up to 6.0505%
     simulation/M_ext agreement: 15939/15939 (100.000%)
[OK] figures/latency10-over-correction-bubble-chart-spike.pdf
     9678 unstable cells, full-block share up to 52.26%, inflation up to 6.2034%
     simulation/M_ext agreement: 15939/15939 (100.000%)
```

Add `--summary-json figures/summary.json` to store the per-panel summary, which carries
the critical elasticity as `minimum_unstable_parameter`, its inbound band as
`minimum_unstable_alpha` and `maximum_unstable_alpha_at_minimum_parameter`, and the
contraction as `boundary_reduction_from_16`.

## Rerun the sweep

From the artifact root, after `./build.sh`:

```bash
./bin/appendix-sweep -figure fig12 -output-dir appendix/figure-12-varying-dmax/data
python3 mext-criterion/mext_criterion.py fig12 appendix/figure-12-varying-dmax/data/dmax5/*.csv  --max-delay 5  --in-place
python3 mext-criterion/mext_criterion.py fig12 appendix/figure-12-varying-dmax/data/dmax7/*.csv  --max-delay 7  --in-place
python3 mext-criterion/mext_criterion.py fig12 appendix/figure-12-varying-dmax/data/dmax10/*.csv --max-delay 10 --in-place
```

The sweep writes the six grids into the three `dmax*` subdirectories itself. `fig12`
requires `--max-delay` because the delay is not recoverable from the CSV rows alone.
