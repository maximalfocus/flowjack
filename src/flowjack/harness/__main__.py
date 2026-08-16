"""Command-line shell over the harness engine.

Deliberately thin: it parses arguments, builds a config, calls :func:`run_harness`, and prints the
transcript. Everything worth testing lives in the engine and is tested directly.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import httpx

from flowjack.config import SHOW_ID, load_settings
from flowjack.harness.engine import HarnessConfig, run_harness
from flowjack.harness.ledger import VERDICT_ABSENT, VERDICT_HELD
from flowjack.harness.transcript import render


def _wait_for_health(client: httpx.Client, attempts: int = 60) -> None:
    for _ in range(attempts):
        try:
            if client.get("/healthz", timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise SystemExit("application did not become healthy")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m flowjack.harness",
        description="Run the sensitive business flow at volume and reconcile the allocation.",
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("FLOWJACK_BASE_URL", "http://secure-app:8000")
    )
    parser.add_argument("--show-id", default=SHOW_ID)
    parser.add_argument("--operator-identities", type=int, default=60)
    parser.add_argument("--operator-seats-per-identity", type=int, default=4)
    parser.add_argument("--genuine-patrons", type=int, default=40)
    parser.add_argument("--genuine-seats-each", type=int, default=2)
    parser.add_argument(
        "--concurrency",
        type=int,
        default=8,
        help="threads used to shorten the run; not part of the demonstrated mechanism",
    )
    parser.add_argument("--pace-seconds", type=float, default=0.0)
    parser.add_argument(
        "--expect",
        choices=[VERDICT_HELD, VERDICT_ABSENT],
        default=None,
        help="exit non-zero unless the run reaches this verdict",
    )
    parser.add_argument("--transcript-path", default=None)
    parser.add_argument("--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = HarnessConfig(
        show_id=args.show_id,
        operator_identities=args.operator_identities,
        operator_seats_per_identity=args.operator_seats_per_identity,
        genuine_patrons=args.genuine_patrons,
        genuine_seats_each=args.genuine_seats_each,
        concurrency=args.concurrency,
        pace_seconds=args.pace_seconds,
    )

    with httpx.Client(base_url=args.base_url, timeout=30.0) as client:
        _wait_for_health(client)
        result = run_harness(client, config, load_settings())

    transcript = render(result, config, verbose=args.verbose)
    print(transcript)
    if args.transcript_path:
        path = Path(args.transcript_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(transcript, encoding="utf-8")
        print(f"transcript written to {path}")

    ledger = result.require_ledger()
    if args.expect is not None and ledger.verdict != args.expect:
        print(f"EXPECTED verdict {args.expect!r}, got {ledger.verdict!r}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
