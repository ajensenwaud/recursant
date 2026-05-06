"""Continuous traffic generator for the mortgage demo.

Loops the end-to-end mortgage flow on a configurable interval so the
mesh observability visualiser is never empty during a screen recording
or live pitch. Stop with Ctrl-C.

Usage:
    python demo/mortgage/scripts/generate_demo_traffic.py
    python demo/mortgage/scripts/generate_demo_traffic.py --interval 8
    python demo/mortgage/scripts/generate_demo_traffic.py --ws-url ws://localhost:8031/api/ws --interval 5
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

# Reuse the existing e2e runner — it already exercises every agent and
# every interceptor in a single mortgage application journey.
sys.path.insert(0, str(Path(__file__).parent))
import test_e2e  # noqa: E402


async def _run_once(ws_url: str) -> bool:
    """Run a single mortgage application end-to-end. Returns success/failure."""
    runner = test_e2e.TestRunner(ws_url)
    try:
        # TestRunner.run() returns 0 on success, non-zero on failure.
        return (await runner.run()) == 0
    except Exception as exc:  # network blip, agent restart, etc.
        print(f"  iteration error: {type(exc).__name__}: {exc}", flush=True)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ws-url",
        default=test_e2e.DEFAULT_WS_URL,
        help=f"Mortgage WebSocket URL (default: {test_e2e.DEFAULT_WS_URL})",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=8.0,
        help="Seconds to sleep between iterations (default: 8)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Stop after N iterations (default: 0 = run forever)",
    )
    args = parser.parse_args()

    print(
        f"Generating continuous mortgage traffic against {args.ws_url}\n"
        f"Interval between iterations: {args.interval}s. Ctrl-C to stop."
    )

    iteration = 0
    success_count = 0
    fail_count = 0
    started = time.time()
    try:
        while True:
            iteration += 1
            print(f"\n--- Iteration {iteration} ---", flush=True)
            ok = asyncio.run(_run_once(args.ws_url))
            if ok:
                success_count += 1
            else:
                fail_count += 1
            elapsed = time.time() - started
            print(
                f"  ok={success_count} fail={fail_count} "
                f"({iteration} runs in {elapsed:.0f}s)",
                flush=True,
            )

            if args.max_iterations and iteration >= args.max_iterations:
                break

            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
