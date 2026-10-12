# Table 3 — estimation tolerance on the deployed chains

Appendix D. The two deployed Cosmos configurations of Table 2, rerun under the
compensated controller of `appendix/figure-16-mitigation`, sweeping the
estimation ratio `gamma = H_i / Lambda_i^delay` at each chain's deployed update
rate. The stable `gamma` interval of each chain is the last column of Table 3.

## Configuration

The same inbound-coupled three-chain surrogate as
`appendix/table-02-deployed-configurations`: `alpha` and `d_max` at each chain's
measured values, the inbound elasticity fixed at 16, spike latency, and the
deployed update rate.

| chain | `alpha` | `d_max` | deployed `delta` | `H_i* = Lambda_0^delay = 16 * alpha` |
|---|---|---|---|---|
| Cosmos Hub | 0.216 | 10 | 0.125 | 3.456 |
| Osmosis | 0.248 | 25 | 0.1 | 3.968 |

The gain is `H_i = gamma * Lambda_i^delay` on every chain, and `gamma` walks
0.00 to 3.00 at step 0.01.

The other columns of Table 3 come from elsewhere: the deployed rates and the
plain-EIP-1559 maximum stable rates, 0.056 for Cosmos Hub and 0.019 for
Osmosis, are the `deployed-update-rate` sweep of
`appendix/table-02-deployed-configurations`, and `H_i^*` is `Lambda_0^delay`
above.

## Data

| file | grid |
|---|---|
| `data/mitigation_deployed_Spike.csv` | `gamma` 0.00 to 3.00 at step 0.01, both chains (602 rows) |

Columns: `chain`, `alpha_inflow`, `d_max`, `delta`, `gamma`, `compensation_h0`,
`distribution`, `final_load`, `avg_load`, `load_std`, `load_inflation`,
`converged`, and the three exact-criterion columns `mext_rho`, `mext_stable`,
`classification_match`.

## Reproduce

From the artifact root, after `./build.sh`:

```bash
./bin/mitigation-deployed -output-dir appendix/table-03-deployed-compensation/data
python3 mext-criterion/mext_compensated.py deployed appendix/table-03-deployed-compensation/data/mitigation_deployed_Spike.csv --in-place
```

Expected output:

```
cosmoshub: alpha=0.216 d_max=10 deployed delta=0.125 Lambda_delay=3.456 stable gamma in [0.23, 2.66] (holes: 0)
osmosis: alpha=0.248 d_max=25 deployed delta=0.100 Lambda_delay=3.968 stable gamma in [0.30, 2.88] (holes: 0)
wrote 602 deterministic rows to appendix/table-03-deployed-compensation/data/mitigation_deployed_Spike.csv
appendix/table-03-deployed-compensation/data/mitigation_deployed_Spike.csv: 602/602 classifications agree (100.000%)
```

The binary writes the twelve simulation columns and the annotator appends the
three criterion columns in place, so the shipped CSV carries all fifteen. The
sweep takes about twenty seconds and is deterministic.

Both stable intervals are contiguous, which is what the `holes: 0` counts
report. Cosmos Hub converges for 244 of its 301 ratios and Osmosis for 259. The
nonlinear verdicts agree with the exact criterion on all 602 rows.

The edges are sharp. At the Cosmos Hub lower edge, `gamma = 0.22` has
`rho(M_ext) = 1.0003` and `gamma = 0.23` has 0.9985. At its upper edge,
`gamma = 2.66` has 0.9991 and `gamma = 2.67` has 1.0001. On Osmosis the lower
edge runs 1.0002 to 0.9991 across `gamma = 0.29` and 0.30, and the upper edge
runs 0.9999 to 1.0003 across 2.88 and 2.89.

Both chains are unstable at `gamma = 0`, which is plain EIP-1559 at the deployed
rate, with `rho(M_ext) = 1.0393` on Cosmos Hub and 1.0303 on Osmosis. That is the
same verdict the Table 2 sweep reaches, where the deployed 0.125 and 0.1 both
exceed the plain maximum stable rate. Compensation reverses that verdict over a
wide band around the exact gain. Cosmos Hub stays stable for any gain between
0.23 and 2.66 times `H_i*`, and Osmosis between 0.30 and 2.88 times, so neither
chain needs a precise elasticity estimate to recover.
