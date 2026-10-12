#!/usr/bin/env bash
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$ROOT/bin"
cd "$ROOT/simulator"
go build -o "$ROOT/bin/" ./cmd/...
go build -o "$ROOT/bin/simulate" .
ls "$ROOT/bin"
