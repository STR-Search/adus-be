#!/usr/bin/env python3
"""Measure the raw network round trip from this machine to the database.

Times ``SELECT 1`` on one already-open connection, so the number is network
latency plus a negligible query — the cost every extra query in a request
multiplies. Also times opening a fresh connection (TCP + TLS + auth), which is
what a cold pool pays. Run it wherever the API runs: locally, and in a Render
shell for the deployed service.

Usage:
    uv run python scripts/db_rtt.py -n 30
"""
import argparse
import asyncio
import statistics
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text

from app.core.database import engine


async def measure(n: int) -> None:
    start = time.perf_counter()
    async with engine.connect() as conn:
        connect_ms = (time.perf_counter() - start) * 1000
        await conn.execute(text("SELECT 1"))  # also opens the transaction
        rtts = []
        for _ in range(n):
            start = time.perf_counter()
            await conn.execute(text("SELECT 1"))
            rtts.append((time.perf_counter() - start) * 1000)
    await engine.dispose()

    rtts.sort()
    print(f"new connection (TCP+TLS+auth): {connect_ms:.1f} ms")
    print(
        f"SELECT 1 round trip  n={n}  min={rtts[0]:.1f}  "
        f"p50={statistics.median(rtts):.1f}  "
        f"p95={rtts[min(n - 1, round(0.95 * (n - 1)))]:.1f}  max={rtts[-1]:.1f} ms"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Measure DB round-trip latency.")
    parser.add_argument("-n", type=int, default=30)
    asyncio.run(measure(parser.parse_args().n))


if __name__ == "__main__":
    main()
