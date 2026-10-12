# Figures 7 and 8 — Amplification factors against channel strength

Appendix B.1. Two diagnostic indicators test whether a delayed pathway is an effective
instability mechanism. Each is the ratio of a past deviation to the current one,
weighted by the delay distribution and masked to the episodes where the two interfere
in the direction the pathway requires. The deviation is a chain's base fee minus its
equilibrium value of 1.

`kappa_def` measures Channel III, the delayed self-feedback that carries Pathway 1, and
masks on same-sign deviations:

```
kappa_def,i(t) = sum_d w_d * |dx_i(t-d) / dx_i(t)| * 1(dx_i(t-d) * dx_i(t) > 0)
```

`kappa_att` measures Channel IV, the delayed peer feedback of Pathway 2-1, and masks on
opposite signs instead. Chain 0 has two peers, so `kappa_att` averages their two
90th percentiles and takes the larger of their two maxima.

## What the statistic is, and why

Both indicators divide by the **current** deviation. On the steps where the trajectory
crosses equilibrium that denominator approaches zero and the ratio diverges, so the
mean and the maximum are both dominated by a handful of isolated steps rather than by
the amplification being measured. These figures therefore report the **90th percentile**
of the per-step kappa series, which is insensitive to those crossings.

The maximum is still plotted alongside it as an extreme-case view, but it should not be
read as evidence of a trend. Under spike latency the 90th percentile peaks at
`epsilon_j0 = 2.5` while the maximum peaks at `epsilon_j0 = 8.0`.

## Result

| | Spike | Uniform | Bimodal |
|---|---|---|---|
| `kappa_def` 90th-percentile peak (Figure 7a) | **11.78** | 5.63 | 5.45 |
| reached at `epsilon_j0`, `alpha_j0_in` | 2.5, 0.163 | 4.5, 0.286 | 4.0, 0.255 |
| `kappa_def` maximum (Figure 7b) | 1.436e+05 | 1.388e+05 | 8.09e+04 |
| `kappa_att` 90th-percentile peak (Figure 8a) | 3.32 | 1.94 | 1.99 |
| reached at `lambda_j0`, `alpha_j0_in` | 5.5, 0.347 | 1.5, 0.102 | 1.5, 0.102 |
| `kappa_att` maximum (Figure 8b) | 4.38 | 1.94 | 1.99 |

Two things follow. Spike latency amplifies about twice as strongly as the dispersed
shapes and reaches its peak at a lower channel intensity, which is why it concentrates
a past deviation into a single step. And `kappa_def` stays above `kappa_att` at 95 of
the 99 swept points, with its spike peak 3.6x the `kappa_att` spike peak, which is why
Pathway 1 is an effective instability mechanism and Pathway 2-1 is not.

`kappa_att` under spike latency has no sharp peak at all. It starts at 2.69 at
`lambda_j0 = 0`, rises to 3.32 at `lambda_j0 = 5.5`, and falls to 1.19 at
`lambda_j0 = 16`. Strengthening the peer channel does not drive the indicator up.

## Layout

```
run_kappa_sweeps.py               drives bin/kappa-fees over both sweeps
plot_kappa_curves.py              draws the four panels from the CSVs
defense-channel/kappa_scan_*.csv  Figure 7, one file per latency shape
attack-channel/kappa_scan_*.csv   Figure 8, one file per latency shape
figures/                          rendered PDFs, created on the first plot run
```

Each CSV holds 33 rows, one per sweep point. The columns are `distribution`, the swept
parameter (`epsilon_j0` in `defense-channel/`, `lambda_j0` in `attack-channel/`),
`alpha_j0_in`, `p90_kappa` and `max_kappa`.

Both sweeps walk their elasticity from 0.0 to 16.0 in steps of 0.5, with the inbound
ratio mapped linearly onto `[0.01, 0.99]`, under all three latency shapes at
`d_max = 5`. The defense sweep raises `epsilon_j0` on both peers, the attack sweep
raises `lambda_j0`. Every other entry of the two elasticity matrices stays at 1.5,
apart from the zero diagonal of `epsilon`, and `delta` stays at 0.125.

Each point is one 50,100-block trajectory of the common protocol, 100 blocks of warm-up
and then the 50,000 measured blocks, following the same one-block 1.01x shock on
Chain 0's source-side demand that every other experiment in the artifact uses. The shock
lands at block 100. The kappa series starts at block 105, where a full five-block delay
window first sits behind the current step, and runs to block 50,099, so the window holds
49,995 candidate steps.

Kappa divides a past deviation by the current one, so a step whose current deviation is
below `1e-12` carries no information and is dropped. A converging trajectory sits at the
equilibrium fee for almost its whole horizon, so the retained sample count varies by
point. It runs from 75 steps at the sharpest points to the full 49,995 where the
trajectory never settles. The headline `kappa_def = 11.777` at `epsilon_j0 = 2.5` under
spike latency is the 90th percentile of 75 retained steps.

## Reproduce the figures

```bash
python3 plot_kappa_curves.py
```

Expected output, with the absolute path of each written file abbreviated:

```
[attack] Spike: p90 peaks at 3.32 at lambda_j0 = 5.5, max peaks at 4.379
[attack] Uniform: p90 peaks at 1.94 at lambda_j0 = 1.5, max peaks at 1.941
[attack] Bimodal: p90 peaks at 1.99 at lambda_j0 = 1.5, max peaks at 1.993
[OK] .../figures/fig8a_p90_attack.pdf
[OK] .../figures/fig8b_max_attack.pdf
[defense] Spike: p90 peaks at 11.78 at epsilon_j0 = 2.5, max peaks at 1.436e+05
[defense] Uniform: p90 peaks at 5.63 at epsilon_j0 = 4.5, max peaks at 1.388e+05
[defense] Bimodal: p90 peaks at 5.45 at epsilon_j0 = 4.0, max peaks at 8.09e+04
[OK] .../figures/fig7a_p90_defense.pdf
[OK] .../figures/fig7b_max_defense.pdf
```

The attack panels are drawn first because the script walks the two modes in
alphabetical order. `--mode defense` or `--mode attack` draws one pair on its own, and
`--output-dir` writes the PDFs elsewhere.

| paper | file |
|---|---|
| Figure 7a | `figures/fig7a_p90_defense.pdf` |
| Figure 7b | `figures/fig7b_max_defense.pdf` |
| Figure 8a | `figures/fig8a_p90_attack.pdf` |
| Figure 8b | `figures/fig8b_max_attack.pdf` |

## Rerun the sweeps

These figures carry no `data/` directory and no boundary sweep. They drive
`bin/kappa-fees`, which runs one configuration and writes the base-fee trajectory of
all three chains as raw little-endian float64. The two kappa definitions are applied in
Python, where they were defined. Build the simulator first.

```bash
./build.sh                                    # from the artifact root
cd appendix/figure-07-08-kappa-amplification
python3 run_kappa_sweeps.py --mode defense
python3 run_kappa_sweeps.py --mode attack
```

`--total-steps 50100` and `--mempool 20` are the defaults and are the common protocol,
so neither needs to be passed. The two sweeps together take well under a minute. Each
prints one line per point and then a summary per latency shape:

```
[defense] Spike: p90 peaks at 11.78, max peaks at 1.436e+05
[defense] Uniform: p90 peaks at 5.63, max peaks at 1.388e+05
[defense] Bimodal: p90 peaks at 5.45, max peaks at 8.09e+04
```

```
[attack] Spike: p90 peaks at 3.32, max peaks at 4.379
[attack] Uniform: p90 peaks at 1.94, max peaks at 1.941
[attack] Bimodal: p90 peaks at 1.99, max peaks at 1.993
```

Each run overwrites the three `kappa_scan_*.csv` files of its own channel directory.
The sweep is deterministic, so it reproduces the shipped CSVs byte for byte. Use
`--output-dir` to write to a scratch directory instead.
