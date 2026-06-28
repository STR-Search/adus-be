#!/usr/bin/env python3
"""Analyze a structlog console dump and report where wall-clock time goes.

Usage:
    uv run python scratch_pad/analyze_log.py scratch_pad/log_output.txt
    uv run python scratch_pad/analyze_log.py scratch_pad/log_output.txt --gap-ms 50 --top 25

What it tells you:
  * how many log lines there are
  * the per-line gap to the *next* line (i.e. work done between them)
  * average cost of actually emitting a debug line (the tiny sub-ms gaps)
  * the biggest gaps, which are almost always I/O (DB queries / network), not logging
  * a focused breakdown of the market->percentiles lookup (the known bottleneck),
    matched per occurrence

It handles both:
  * a clean structlog ConsoleRenderer dump:
        2026-06-28T10:42:56.367628Z [debug    ] some.event.name  key=value
  * a raw GitHub Actions download, which prefixes its own timestamp and wraps
    everything in ANSI color codes:
        2026-06-28T10:42:56.368Z \x1b[2m2026-06-28T10:42:56.367628Z\x1b[0m [\x1b[32m\x1b[1mdebug ...
    The GH prefix timestamp and all ANSI escapes are stripped; the inner
    structlog timestamp is the one used for timing.
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime

# Strip ANSI SGR color codes (ESC [ ... m) that the raw GitHub log is full of.
ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Find the structlog timestamp that sits immediately before "[level]".
# Using search (not match) lets us skip any leading GitHub-Actions timestamp
# prefix: that one is followed by another timestamp, not by "[", so it never
# matches here — the engine lands on the real structlog timestamp.
LINE_RE = re.compile(
    r"(?P<ts>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{1,6})\d*Z?\s+"
    r"\[\s*(?P<level>\w+)\s*\]\s+"
    r"(?P<event>.*?)\s*$"
)
TS_FMT = "%Y-%m-%dT%H:%M:%S.%f"

# Markers for the focused bottleneck breakdown. Each gap is measured from the
# START marker line to the END marker line within the same property cycle.
START_MARKER = "market lookup"
END_MARKER = "percentiles lookup"

# --- File window ---------------------------------------------------------
# GitHub Actions wraps the real app output in setup/teardown noise. We only
# want the slice between these two boundaries:
#   * begin reading on the line AFTER the last line whose content is BOUNDARY_START
#   * stop reading on the line BEFORE the first line whose content is BOUNDARY_END
# Both are matched against the line content with the leading GitHub timestamp and
# ANSI codes stripped, compared exactly (trimmed). Set either to None to disable
# that boundary (read from the very start / to the very end).
BOUNDARY_START = "##[endgroup]"   # last GH setup marker before the app boots
BOUNDARY_END = "{"                # first standalone "{" — start of the trailing JSON dump

# Strip a leading GitHub-Actions timestamp prefix ("2026-...Z ") if present.
GH_PREFIX_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z?\s+")


def _content(raw: str) -> str:
    """The line stripped of ANSI codes and any leading GH timestamp, trimmed."""
    c = ANSI_RE.sub("", raw.rstrip("\n"))
    c = GH_PREFIX_RE.sub("", c)
    return c.strip()


def _window(raw_lines: list[str]) -> tuple[list[str], int, int]:
    """Slice raw_lines to the [BOUNDARY_START, BOUNDARY_END) window.

    Returns (sliced_lines, start_idx, end_idx). end_idx is found first; the start
    is the LAST BOUNDARY_START occurring *before* end_idx, so trailing GH "Post"
    steps that re-emit ##[endgroup] don't push the start past the app output.
    """
    contents = [_content(r) for r in raw_lines]

    end_idx = len(raw_lines)
    if BOUNDARY_END is not None:
        for i, c in enumerate(contents):
            if c == BOUNDARY_END:
                end_idx = i
                break

    start_idx = 0
    if BOUNDARY_START is not None:
        for i in range(end_idx):
            if contents[i] == BOUNDARY_START:
                start_idx = i + 1  # begin on the line AFTER the marker

    return raw_lines[start_idx:end_idx], start_idx, end_idx


def parse(path: str):
    """Return (rows, window_info) where rows is a list of (datetime, event_text).

    Only lines inside the BOUNDARY_START -> BOUNDARY_END window are considered.
    Lines that don't match the log format (continuations, blanks, tracebacks)
    are skipped so a messy dump still analyzes cleanly.
    """
    with open(path, "r", errors="replace") as fh:
        raw_lines = fh.readlines()

    sliced, start_idx, end_idx = _window(raw_lines)
    window_info = {
        "total_lines": len(raw_lines),
        "start_idx": start_idx,
        "end_idx": end_idx,
        "window_lines": len(sliced),
    }

    rows = []
    for raw in sliced:
        clean = ANSI_RE.sub("", raw.rstrip("\n"))
        m = LINE_RE.search(clean)
        if not m:
            continue
        try:
            ts = datetime.strptime(m.group("ts"), TS_FMT)
        except ValueError:
            continue
        # keep just the human event label, drop the key=value tail for readability
        event = m.group("event")
        event = re.split(r"\s{2,}|\s+\w+=", event, maxsplit=1)[0].strip()
        rows.append((ts, event or m.group("event").strip()))
    return rows, window_info


def fmt_dur(seconds: float) -> str:
    if seconds >= 1:
        return f"{seconds:7.3f} s"
    return f"{seconds * 1000:7.2f} ms"


def main() -> int:
    ap = argparse.ArgumentParser(description="Analyze a structlog console dump.")
    ap.add_argument("logfile", help="path to the .txt log dump")
    ap.add_argument("--gap-ms", type=float, default=50.0,
                    help="gaps larger than this (ms) are treated as I/O waits, not logging (default 50)")
    ap.add_argument("--top", type=int, default=20,
                    help="how many of the biggest gaps to list (default 20)")
    args = ap.parse_args()

    rows, win = parse(args.logfile)
    if len(rows) < 2:
        print(f"Only parsed {len(rows)} log line(s) from {args.logfile!r} — nothing to analyze.")
        print(f"(window: lines {win['start_idx']+1}-{win['end_idx']} of {win['total_lines']}; "
              f"check BOUNDARY_START / BOUNDARY_END markers.)")
        return 1

    times = [t for t, _ in rows]
    total_span = (times[-1] - times[0]).total_seconds()

    # gap[i] = time between line i and line i+1 (work done after emitting line i)
    gaps = [(times[i + 1] - times[i]).total_seconds() for i in range(len(rows) - 1)]
    threshold = args.gap_ms / 1000.0

    log_gaps = [g for g in gaps if g <= threshold]   # logging overhead + trivial compute
    io_gaps = [g for g in gaps if g > threshold]      # DB / network waits

    print("=" * 70)
    print(f"LOG ANALYSIS — {args.logfile}")
    print("=" * 70)
    print(f"Window analyzed        : lines {win['start_idx']+1}-{win['end_idx']} "
          f"of {win['total_lines']} "
          f"(after {BOUNDARY_START!r}, before {BOUNDARY_END!r})")
    print(f"Total log lines parsed : {len(rows)} (of {win['window_lines']} in window)")
    print(f"Total wall-clock span  : {fmt_dur(total_span)}")
    print()
    print(f"Split at {args.gap_ms:g} ms threshold:")
    if log_gaps:
        print(f"  Logging/compute gaps (<= {args.gap_ms:g} ms): "
              f"{len(log_gaps):>5} lines, "
              f"avg {sum(log_gaps)/len(log_gaps)*1000:6.3f} ms/line, "
              f"total {fmt_dur(sum(log_gaps))}")
    if io_gaps:
        print(f"  I/O waits           (>  {args.gap_ms:g} ms): "
              f"{len(io_gaps):>5} gaps,  "
              f"total {fmt_dur(sum(io_gaps))} "
              f"({sum(io_gaps)/total_span*100:.1f}% of wall-clock)")
    print()
    print("  => Logging itself costs ~{:.3f} ms/line. The wall-clock is dominated"
          .format(sum(log_gaps)/len(log_gaps)*1000 if log_gaps else 0))
    print("     by the I/O waits below, not by writing logs.")
    print()

    # --- biggest gaps ---
    print("-" * 70)
    print(f"TOP {args.top} BIGGEST GAPS (where the time actually goes)")
    print("-" * 70)
    ranked = sorted(range(len(gaps)), key=lambda i: gaps[i], reverse=True)[:args.top]
    for rank, i in enumerate(ranked, 1):
        print(f"{rank:>3}. {fmt_dur(gaps[i])}  after: {rows[i][1][:60]!r}")
    print()

    # --- per-event profile: auto-detect recurring events, attribute the gap ---
    # The gap AFTER a line is the work triggered by that line's operation, so we
    # attribute gaps[i] to rows[i]'s event. This surfaces slow operations even
    # when you don't know the marker names up front.
    print("-" * 70)
    print(f"PER-EVENT PROFILE (gap after each line attributed to that event)")
    print("-" * 70)
    agg: dict[str, list[float]] = {}
    for i in range(len(gaps)):
        agg.setdefault(rows[i][1], []).append(gaps[i])

    profile = [
        (ev, sum(ds), len(ds), sum(ds) / len(ds), max(ds))
        for ev, ds in agg.items()
    ]
    profile.sort(key=lambda r: r[1], reverse=True)

    print(f"{'total':>11}  {'n':>4}  {'avg':>10}  {'max':>10}  event")
    for ev, total, n, avg, mx in profile[:args.top]:
        print(f"{fmt_dur(total)}  {n:>4}  {fmt_dur(avg)}  {fmt_dur(mx)}  {ev[:48]}")
    shown = sum(r[1] for r in profile[:args.top])
    if len(profile) > args.top:
        rest = sum(r[1] for r in profile[args.top:])
        print(f"  ... +{len(profile)-args.top} more events, {fmt_dur(rest)} total")
    print(f"\n  Distinct events: {len(profile)}.  Top {min(args.top, len(profile))} "
          f"account for {shown/total_span*100:.1f}% of wall-clock.")
    print()

    # --- focused: market -> percentiles lookup, matched per occurrence ---
    print("-" * 70)
    print(f"FOCUSED: {START_MARKER!r} -> {END_MARKER!r} durations")
    print("-" * 70)
    occurrences = []
    pending_start = None
    for idx, (t, ev) in enumerate(rows):
        low = ev.lower()
        if START_MARKER in low:
            pending_start = (idx, t)
        elif END_MARKER in low and pending_start is not None:
            dur = (t - pending_start[1]).total_seconds()
            occurrences.append((len(occurrences) + 1, dur, pending_start[0], idx))
            pending_start = None

    if occurrences:
        for n, dur, si, ei in occurrences:
            print(f"  #{n}: {fmt_dur(dur)}   (lines {si+1} -> {ei+1})")
        durs = [d for _, d, _, _ in occurrences]
        print()
        print(f"  count={len(durs)}  "
              f"min={fmt_dur(min(durs))}  "
              f"max={fmt_dur(max(durs))}  "
              f"avg={fmt_dur(sum(durs)/len(durs))}  "
              f"total={fmt_dur(sum(durs))}")
        print(f"\n  => {sum(durs)/total_span*100:.1f}% of the whole operation is spent in this one lookup.")
    else:
        print(f"  No {START_MARKER!r} -> {END_MARKER!r} pairs found.")
        print("  (Adjust START_MARKER / END_MARKER at the top of this script to match your events.)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
