"""Command-line shell over the comparison engine.

Deliberately thin, for the same reason the harness CLI is: everything worth testing lives in the
engine and the report, and both are tested directly.
"""

from __future__ import annotations

import argparse
import sys
import time
from contextlib import ExitStack
from pathlib import Path

import httpx

from flowjack.compare.engine import DEFAULT_TARGETS, ComparisonTarget, run_comparison
from flowjack.compare.report import render
from flowjack.config import load_settings
from flowjack.harness.engine import Client


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m flowjack.compare",
        description="Run every scenario and print the comparison.",
    )
    parser.add_argument(
        "--host-template",
        default="http://{service}:8000",
        help="how to reach each scenario's application, given its Compose service name",
    )
    parser.add_argument("--transcript-path", default=None)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--require-contrast",
        action="store_true",
        help="exit non-zero unless at least one row is SECURE and at least one is VULNERABLE",
    )
    return parser


def _wait_for_health(client: httpx.Client) -> None:
    for _ in range(60):
        try:
            if client.get("/healthz", timeout=2.0).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(1.0)
    raise SystemExit(f"application at {client.base_url} did not become healthy")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    with ExitStack() as stack:

        def open_client(target: ComparisonTarget) -> Client:
            client = stack.enter_context(
                httpx.Client(
                    base_url=args.host_template.format(service=target.service), timeout=60.0
                )
            )
            _wait_for_health(client)
            return client

        rows = run_comparison(open_client, DEFAULT_TARGETS, load_settings())

    report = render(rows, verbose=args.verbose)
    print(report)
    if args.transcript_path:
        path = Path(args.transcript_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(report, encoding="utf-8")
        print(f"comparison written to {path}")

    if args.require_contrast and not (
        any(row.secure for row in rows) and any(not row.secure for row in rows)
    ):
        print("EXPECTED both a SECURE and a VULNERABLE row", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
