#!/usr/bin/env bash
set -e

: "${MOONBEAM_RPC_URL:=https://rpc.api.moonbeam.network}"
: "${ETH_RPC_URL:?set ETH_RPC_URL to an Ethereum JSON-RPC endpoint}"

mkdir -p data/moonbeam_2025-03-21
python3 fetch_fee_range.py \
  --from-ts "2025-03-21T00:00:00Z" --to-ts "2025-03-22T00:00:00Z" \
  --eth-rpc "${MOONBEAM_RPC_URL}" \
  --chain "moonbeam" \
  --output "data/moonbeam_2025-03-21/moonbeam_fee_range_2025-03-21.csv" \
  --force-manual \
  --tip-percentile 50 --verbose

mkdir -p data/eth_2025-12-23
python3 fetch_fee_range.py \
  --from-ts "2025-12-23T00:00:00Z" --to-ts "2025-12-24T00:00:00Z" \
  --eth-rpc "${ETH_RPC_URL}" \
  --chain "eth" \
  --output "data/eth_2025-12-23/eth_fee_range_2025-12-23.csv" \
  --tip-percentile 50 --verbose
