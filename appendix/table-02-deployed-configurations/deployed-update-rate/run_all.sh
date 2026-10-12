#!/usr/bin/env bash
# Rerun each of Table 2's six chains under its measured configuration.
#
# Arguments are the measured inbound ratio, the measured delay d_max, the
# deployed update rate, and the trace file. Every run assumes Ethereum's
# elasticity of 16 on the inbound flows, spike latency, and the Section 7.1
# protocol. Each invocation sweeps delta from 0.001 to 0.300 to locate the
# chain's maximum stable rate, then writes the 50,000-block trace at the
# deployed rate.
set -e

BIN="${DEPLOYED_CHAIN_BIN:-../../../bin/deployed-chain}"
mkdir -p traces

"$BIN" 0.134 7  0.000075 traces/assethub_delta7.5e-5_dmax7.csv
"$BIN" 0.060 7  0.000075 traces/bifrost_delta7.5e-5_dmax7.csv
"$BIN" 0.133 7  0.000075 traces/hydration_delta7.5e-5_dmax7.csv
"$BIN" 0.255 7  0.004    traces/moonbeam_delta0.004_dmax7.csv
"$BIN" 0.216 10 0.125    traces/cosmoshub_delta0.125_dmax10.csv
"$BIN" 0.248 25 0.1      traces/osmosis_delta0.1_dmax25.csv
