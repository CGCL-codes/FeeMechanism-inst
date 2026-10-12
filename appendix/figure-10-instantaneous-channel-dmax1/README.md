# Figure 10 — The instantaneous peer channel isolated at d_max = 1

Appendix B.1. Figure 9's bottom row cannot separate Channel II from the delayed
channels of the peer chains, because strengthening one strengthens the other. Setting
`d_max = 1` switches the peers' delayed feedback channel off entirely and leaves
Channel II as the only active peer coupling.

Output: `figures/boundary-attack-without-latency.pdf`.

Only 77 of 15,939 configurations fail the convergence criterion, a share of 0.48%. The
first failure appears at `epsilon_0j = 14.5` with a 99% outbound ratio. Of those 77
failures, 71 never fill a block, and the worst of the other six fills 10.54% of its
blocks. `M_ext` agrees with the simulation on all 15,939 configurations. Channel II
therefore produces a narrow instability region under extreme conditions only, and it
does not reproduce the broad amplification of Pathway 1.

## Data

`data/attack_defense_results_Spike.csv` — spike latency at `d_max = 1`, `epsilon_0j`
from 16.0 down to 0.0 at step 0.1 against `alpha_outflow` from 0.99 down to 0.01. That is
15,939 points.

## Reproduce the figure

```bash
python3 plot_boundary.py --figure fig10 --input-dir data --output-dir figures --summary-json figures/summary.json
```

`--summary-json` writes the shipped summary file.

## Rerun the sweep

From the artifact root, after `./build.sh`:

```bash
./bin/appendix-sweep -figure fig10 -output-dir appendix/figure-10-instantaneous-channel-dmax1/data
python3 mext-criterion/mext_criterion.py fig10 appendix/figure-10-instantaneous-channel-dmax1/data/*.csv --in-place
```
