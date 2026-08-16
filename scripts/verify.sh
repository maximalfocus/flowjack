#!/usr/bin/env bash
# The one documented command. Brings up the secure application on a hermetic, egress-less
# network, runs linters, types, the test suite, and the HTTP walkthrough inside that network,
# then tears everything down. Nothing survives the run.
#
# Local verification and GitHub Actions invoke this identical boundary.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$root"

cleanup() {
  docker compose down --remove-orphans --volumes >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Fresh state every run: no container, network, or volume is reused.
cleanup

docker compose build
docker compose run --rm --build verify
