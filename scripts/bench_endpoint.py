#!/usr/bin/env python3
"""Hit one endpoint N times and summarise client + server-side latency.

Run the same command against every environment so the numbers compare. Server
breakdown comes from the ``Server-Timing`` header, so the target must run with
``PROFILING_ENABLED=true``; without it only client-side timings are reported.

The first ``--warmup`` requests are discarded: they pay for DNS, TLS, and a
cold DB pool, which is real but not what the steady-state numbers are about.
Pass ``--fresh`` to open a new HTTP connection per request instead.

Usage:
    ADUS_API_KEY=... uv run python scripts/bench_endpoint.py \\
        --base-url http://localhost:8000 --label local -n 20
    ADUS_API_KEY=... uv run python scripts/bench_endpoint.py \\
        --base-url https://<dev>.onrender.com --label render-ohio \\
        --param page_size=100 --out bench-render-ohio.json
"""

import argparse
import json
import os
import re
import statistics
import sys
import time
from pathlib import Path

import httpx

_ENTRY_RE = re.compile(r'^\s*([^;]+)(?:;dur=([\d.]+))?(?:;desc="([^"]*)")?')


def parse_server_timing(header: str | None) -> dict[str, float]:
    timings: dict[str, float] = {}
    for entry in (header or "").split(","):
        match = _ENTRY_RE.match(entry)
        if match and match.group(2) is not None:
            timings[match.group(1).strip()] = float(match.group(2))
    return timings


def percentile(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def summarise(samples: list[dict]) -> dict[str, dict[str, float]]:
    metrics: dict[str, list[float]] = {}
    for sample in samples:
        metrics.setdefault("client_total_ms", []).append(sample["client_total_ms"])
        for name, ms in sample["server"].items():
            metrics.setdefault(f"server.{name}", []).append(ms)
    return {
        name: {
            "p50": round(statistics.median(values), 1),
            "p95": round(percentile(values, 95), 1),
            "max": round(max(values), 1),
        }
        for name, values in metrics.items()
    }


def run(args) -> dict:
    headers = {"X-ADUS-API-KEY": args.api_key} if args.api_key else {}
    if args.bearer:
        headers["Authorization"] = f"Bearer {args.bearer}"
    params = [tuple(p.split("=", 1)) for p in args.param]
    url = f"{args.base_url.rstrip('/')}{args.path}"

    samples: list[dict] = []
    client = None if args.fresh else httpx.Client(headers=headers, timeout=120)
    try:
        for i in range(args.warmup + args.n):
            start = time.perf_counter()
            if client is None:
                response = httpx.get(url, params=params, headers=headers, timeout=120)
            else:
                response = client.get(url, params=params)
            elapsed = (time.perf_counter() - start) * 1000
            if response.status_code != 200:
                sys.exit(f"HTTP {response.status_code}: {response.text[:500]}")
            if i < args.warmup:
                continue
            samples.append(
                {
                    "client_total_ms": round(elapsed, 2),
                    "response_bytes": len(response.content),
                    "server": parse_server_timing(
                        response.headers.get("server-timing")
                    ),
                }
            )
    finally:
        if client is not None:
            client.close()

    return {
        "label": args.label,
        "url": url,
        "params": params,
        "n": args.n,
        "fresh_connections": args.fresh,
        "response_bytes": samples[-1]["response_bytes"],
        "summary": summarise(samples),
        "samples": samples,
    }


def print_report(report: dict) -> None:
    print(f"\n{report['label']}  {report['url']}  params={report['params']}")
    print(f"n={report['n']}  response={report['response_bytes'] / 1024:.1f} KiB")
    print(f"{'metric':<40}{'p50':>10}{'p95':>10}{'max':>10}")
    for name, stats in report["summary"].items():
        print(f"{name:<40}{stats['p50']:>10}{stats['p95']:>10}{stats['max']:>10}")
    if not any(name.startswith("server.") for name in report["summary"]):
        print("(no Server-Timing header — is PROFILING_ENABLED set on the target?)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark an ADUS endpoint.")
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--path", default="/iron-bank/underwritings")
    parser.add_argument("--param", action="append", default=[], help="k=v, repeatable")
    parser.add_argument("--label", default="run", help="e.g. local, render-ohio")
    parser.add_argument("-n", type=int, default=20)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument(
        "--fresh", action="store_true", help="new connection per request"
    )
    parser.add_argument("--api-key", default=os.environ.get("ADUS_API_KEY"))
    parser.add_argument("--bearer", default=os.environ.get("ADUS_BEARER_TOKEN"))
    parser.add_argument("--out", type=Path, help="write the full report as JSON")
    args = parser.parse_args()
    if not (args.api_key or args.bearer):
        sys.exit("Set ADUS_API_KEY (or ADUS_BEARER_TOKEN), or pass --api-key.")

    report = run(args)
    print_report(report)
    if args.out:
        args.out.write_text(json.dumps(report, indent=2))
        print(f"\nwrote {args.out}")


if __name__ == "__main__":
    main()
