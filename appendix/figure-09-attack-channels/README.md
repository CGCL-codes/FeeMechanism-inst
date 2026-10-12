# Figure 9 — Stability boundary while strengthening the peer channels

Appendix B.1. Pathway 2 proposes two ways a peer chain could destabilise Chain 0. This
experiment strengthens each of them in turn and looks for a boundary.

| panel | output |
|---|---|
| 9a, 9b, 9c | `figures/converged-attack-defense-bubble-chart-{bimodal,uniform,spike}.pdf` |
| 9d, 9e, 9f | `figures/attack-defense-bubble-chart-{bimodal,uniform,spike}.pdf` |

Top row, panels a to c: the delayed peer channel `Lambda^delay_ji` (Channel IV),
sweeping the source-side elasticity `lambda_j0` against the inbound ratio.
Bottom row, panels d to f: the instantaneous peer channel `Lambda^inst_ij`
(Channel II), sweeping the destination-side elasticity `epsilon_0j` against the
outbound ratio. Each row covers bimodal, uniform and spike latency at `d_max = 5`.

The top row holds 47,817 configurations, 15,939 for each of the three latency shapes.
Every one of them converges. No chain fills a single block anywhere in the top row, under
any shape. `M_ext` classifies all 47,817 the same way the simulation does. Channel IV
produces no boundary inside the scanned range.

The bottom row does produce a narrow unstable region. Its size depends on the latency
shape.

| shape | failures of 15,939 | first failure | worst full-block share | one-sided `M_ext` disagreements |
|---|---|---|---|---|
| bimodal | 23 | `epsilon_0j = 15.3` at 99% outbound | never fills a block | 906 |
| uniform | 852 | `epsilon_0j = 11.0` at 99% outbound | 46.56% | 760 |
| spike | 4,625 | `epsilon_0j = 5.0` at 99% outbound | 49.94% | 354 |

The first failure is the weakest `epsilon_0j` at which any configuration fails. In all
three shapes it sits at the 99% outbound ratio and at no other ratio in that column.

Every classification disagreement in the bottom row runs the same way. `M_ext` calls the
configuration unstable and the simulation converges. The reverse never happens in any of
the three panels. The `M_ext` boundary is therefore conservative here, because the
symmetric perturbation used in the sweep does not excite every system mode that `M_ext`
covers.

Strengthening `Lambda^inst_ij` on one chain also strengthens the negative-feedback
channels of the connected chains, so the delayed pathways of those chains remain active.
The bottom-row instability cannot be attributed to Channel II alone. Figure 10 isolates
it properly.

## Data

| directory | channel | grid |
|---|---|---|
| `data/delayed-channel/` | `Lambda^delay_ji` | `lambda_j0` 16.0 down to 0.0 at step 0.1, `alpha_inflow` 0.99 down to 0.01 |
| `data/instantaneous-channel/` | `Lambda^inst_ij` | `epsilon_0j` over the same range, `alpha_outflow` over the same range |

161 parameter values by 99 ratios is 15,939 points per latency shape per channel.

## Reproduce the figure

```bash
python3 plot_boundary.py --figure fig9-top    --input-dir data/delayed-channel       --output-dir figures --summary-json figures/summary-delayed.json
python3 plot_boundary.py --figure fig9-bottom --input-dir data/instantaneous-channel --output-dir figures --summary-json figures/summary-instantaneous.json
```

`fig9-top` renders the delayed channel and `fig9-bottom` the instantaneous one. The
script prints a per-panel summary of the boundary location, the classification agreement,
the full-block share and the load inflation. `--summary-json` writes the same numbers to
the two shipped summary files.

## Rerun the sweeps

From the artifact root, after `./build.sh`:

```bash
./bin/appendix-sweep -figure fig9-top    -output-dir appendix/figure-09-attack-channels/data/delayed-channel
./bin/appendix-sweep -figure fig9-bottom -output-dir appendix/figure-09-attack-channels/data/instantaneous-channel
python3 mext-criterion/mext_criterion.py fig9-top    appendix/figure-09-attack-channels/data/delayed-channel/*.csv --in-place
python3 mext-criterion/mext_criterion.py fig9-bottom appendix/figure-09-attack-channels/data/instantaneous-channel/*.csv --in-place
```
