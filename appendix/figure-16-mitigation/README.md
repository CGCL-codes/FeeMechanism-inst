# Figure 16 — the compensated controller

Appendix D. The same three-chain system as Figure 4 (spike latency, `d_max = 5`,
one-block `1.01x` shock, 50,100 steps, pool bounded at 20x the gas limit), rerun
with the compensated update rule

```
x_i(t+1) = x_i(t) * ( 1 + delta_i * [ (L_i(t)-T_i)/T_i
                      - H_i * sum_d w_d (P_i(t)-P_i(t-d))/P_i(t) ] )
```

where the exact gain is `H_i* = Lambda_i^delay = sum_j eps_ji * alpha_{j->i,in}`.
The bracket is clamped to `[-1, 1]`, the range plain EIP-1559's own signal
already occupies, so the base fee stays positive.

| paper | script | output |
|---|---|---|
| Figure 16a, 16b | `plot_mitigation.py` | `figures/mitigation-boundary.pdf` |

Panel (a) is the largest stable update rate against the inbound ratio at
elasticity 16, plain versus compensated, from the exact criterion. Markers give
the nonlinear boundary of Figure 4c. Panel (b) is the stable region over the
estimation ratio `gamma = H_i / Lambda_i^delay`, the deployed gain over the
actual delayed coefficient, so `gamma = 0` is plain EIP-1559 and `gamma = 1`
means the elasticity estimate inside `H_i` is exact.

The deployed-chain sweep behind Table 3 lives in
`../table-03-deployed-compensation`.

## Data

| file | grid |
|---|---|
| `data/mitigation_fig4a_Spike.csv` | `epsilon_j0` 16.0 down to 0.0 at step 0.1, `alpha` 0.99 down to 0.01 at step 0.01, `gamma = 1` (15,939 points) |
| `data/mitigation_fig4c_Spike.csv` | `delta` 0.125 down to 0.001 at step 0.001, same `alpha` grid, `gamma = 1` (12,375 points) |
| `data/mitigation_gamma_Spike.csv` | `delta` 0.200 down to 0.001 at step 0.001, `gamma` 1.5 down to 0.0 at step 0.005, at `alpha = 0.99`, `epsilon_j0 = 16` (60,200 points) |

Columns: the swept parameter, `alpha_inflow`, `gamma`, `compensation_h0`,
`distribution`, `final_load`, `avg_load`, `load_std`, `load_inflation`,
`converged`, `full_block_fraction`, and the three exact-criterion columns
`mext_rho`, `mext_stable`, `classification_match`.

Every row with `gamma = 0` is plain EIP-1559 and reproduces the Figure 4
baseline, which makes the `gamma` file a regression test on the controller
change. On its 200 update rates at `alpha = 0.99` only 18 converge, so the
largest converging `delta` is 0.018 and the boundary sits at 0.019, the Figure
4c value.

## Reproduce the figure

```bash
python3 plot_mitigation.py
```

Expected output:

```
Figure 4a: nonconverged 8008/15939 -> 0/15939; max inflation 0.062568 -> 0.000000; exact agreement 15939/15939
Figure 4c: nonconverged 6806/12375 -> 0/12375; max inflation 0.062149 -> 0.000000; exact agreement 12375/12375
gamma window at delta=0.125, alpha=0.99: [0.750, 1.030]
corner chain 0: Lambda_inst=0.0150, Lambda_delay=15.8400, bound H=0 0.0185 -> bound H=H* 0.1335, 2/(inst+delay)=0.1261
```

These are the appendix's headline numbers. The two grids hold 28,314
configurations between them, 14,814 of which diverge under plain EIP-1559, and
every one of them converges under compensation. The share of full blocks falls
with them. On the Figure 4a grid the largest share drops from 52.74% to zero,
and on the Figure 4c grid from 52.45% to zero. No block reaches the gas limit
anywhere in either mitigated sweep. The exact criterion agrees with the
nonlinear verdict on all 15,939 and all 12,375 configurations.

Panel (a) reads the recovery through the update rate. At an inbound ratio of
0.99 and elasticity 16, the exact bound moves from 0.0185 under plain EIP-1559
to 0.1335 under exact compensation. The nonlinear sweep places the same pair of
boundaries at 0.019 and 0.134, and 0.134 is above Ethereum's deployed 0.125.
The compensated bound tracks `2/(Lambda_0^inst + Lambda_0^delay) = 0.1261`,
which is the rate a chain with no delayed coupling at all would tolerate.

Panel (b) reads it through the estimation ratio. At the deployed `delta = 0.125`
the system converges exactly for `gamma` in [0.750, 1.030], a contiguous window
of 57 of the 301 scanned ratios. Overestimating the delayed coefficient by 3%
already destabilizes the chain, while underestimating it by 25% does not. The
window widens fast as the update rate drops. At `delta = 0.05` the lower edge is
`gamma = 0.405` and the upper edge is past 1.5, the largest ratio scanned, so
that column has no measured upper bound. The `gamma` file agrees with the exact
criterion on 60,195 of its 60,200 points, and each of the five exceptions has
`rho(M_ext)` within 7e-5 of 1.

## Rerun the sweeps

From the artifact root, after `./build.sh`:

```bash
./bin/mitigation-sweep -mode fig4a -output-dir appendix/figure-16-mitigation/data
./bin/mitigation-sweep -mode fig4c -output-dir appendix/figure-16-mitigation/data
./bin/mitigation-sweep -mode gamma -output-dir appendix/figure-16-mitigation/data
python3 mext-criterion/mext_compensated.py fig4a appendix/figure-16-mitigation/data/mitigation_fig4a_Spike.csv --in-place
python3 mext-criterion/mext_compensated.py fig4c appendix/figure-16-mitigation/data/mitigation_fig4c_Spike.csv --in-place
python3 mext-criterion/mext_compensated.py gamma appendix/figure-16-mitigation/data/mitigation_gamma_Spike.csv --in-place
```

Each sweep takes under a minute on eight workers. Every simulation is
deterministic. `mext-criterion/mext_compensated.py` builds `M_ext` with
`Lambda_i^inst + H_i` on the instantaneous diagonal and `Lambda_i^delay - H_i`
on the delayed diagonal, and reduces to `mext_criterion.py` at `H_i = 0`.
