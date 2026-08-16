#!/usr/bin/env bash
# The one documented command. Brings everything up on a hermetic, egress-less network, runs
# linters, types, the test suite, the HTTP walkthrough, and the automation harness inside that
# network, then tears everything down. Nothing survives the run.
#
# Local verification and GitHub Actions invoke this identical boundary.
#
# The vulnerable application is started only in the second phase, and only because this script
# takes BOTH deliberate opt-in actions explicitly and visibly:
#
#   1. --profile vulnerable
#   2. ALLOW_VULNERABLE_DEMO=true
#
# The default `docker compose up` starts neither the vulnerable application nor anything that
# talks to it.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"

cleanup() {
  docker compose --profile vulnerable down --remove-orphans --volumes >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Fresh state every run: no container, network, or volume is reused.
cleanup

docker compose build

echo "### phase 1 — secure application (the default path)"
docker compose run --rm verify

echo
echo "### phase 2 — vulnerable application (opt-in profile + explicit acknowledgement)"
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable run --rm verify-vulnerable

echo
echo "### phase 3 — every scenario side by side"
# Phases 1 and 2 drained these allocations. Each container reseeds its own in-memory database at
# startup, so restarting them is how the comparison gets a fresh 120 seats for every row.
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable restart \
  secure-app-harness vulnerable-app vulnerable-app-abandon vulnerable-app-rate-limit \
  vulnerable-app-quota vulnerable-app-gate vulnerable-app-sequential
ALLOW_VULNERABLE_DEMO=true docker compose --profile vulnerable run --rm verify-compare
