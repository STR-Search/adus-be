"""Opt-in per-request latency profiling, enabled by ``PROFILING_ENABLED``.

Each HTTP request gets a ``RequestProfile`` held in a contextvar. Three things
write into it:

  - ``timed("name")`` spans placed at the interesting steps (auth, repository
    queries, service enrichment). Repeated names accumulate.
  - SQLAlchemy engine hooks that count and time *every* statement, plus the
    pool's pre-ping and new physical connections — round trips that never show
    up as a query but each cost a full network hop to the database.
  - ``ProfilingMiddleware``, which emits one ``request.profile`` log line per
    request and a ``Server-Timing`` header (visible in browser devtools and read
    by ``scripts/bench_endpoint.py``).

With the flag off the middleware and hooks are never installed and ``timed()``
is a contextvar lookup, so the call sites can stay in place permanently.
"""

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logger import logger

_current: ContextVar["RequestProfile | None"] = ContextVar(
    "request_profile", default=None
)

_TABLE_RE = re.compile(r"\bFROM\s+([\w.]+)", re.IGNORECASE)
_WRITE_RE = re.compile(r"^(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+([\w.]+)", re.IGNORECASE)


def _ms(seconds: float) -> float:
    return round(seconds * 1000, 2)


def _query_label(statement: str) -> str:
    """Short, stable label for a statement: verb + primary table.

    Full SQL would make the log line unreadable; the table is what tells the
    selectinloads (``uw_comp_set``, ``uw_taxes``...) apart.
    """
    text = " ".join(statement.split()).replace('"', "")
    write = _WRITE_RE.match(text)
    if write:
        return f"{write.group(1).split()[0].upper()} {write.group(2)}"
    table = _TABLE_RE.search(text)
    name = table.group(1) if table else "?"
    if text.upper().startswith("SELECT COUNT("):
        return f"COUNT {name}"
    return f"{text.split(' ', 1)[0].upper()} {name}"


@dataclass
class RequestProfile:
    method: str
    path: str
    query: str = ""
    started: float = field(default_factory=time.perf_counter)
    spans: dict[str, float] = field(default_factory=dict)
    # (label, ms) in execution order
    queries: list[tuple[str, float]] = field(default_factory=list)
    db_query_ms: float = 0.0
    db_pings: int = 0
    db_ping_ms: float = 0.0
    db_connects: int = 0
    db_connect_ms: float = 0.0
    # Sum of outermost spans only, so "other" (routing, validation, response
    # serialization) can be derived without double-counting nested spans.
    top_level_ms: float = 0.0
    _depth: int = 0
    _connect_started: float | None = None

    def elapsed_ms(self) -> float:
        return _ms(time.perf_counter() - self.started)

    def add_span(self, name: str, ms: float) -> None:
        self.spans[name] = round(self.spans.get(name, 0.0) + ms, 2)

    @property
    def db_round_trips(self) -> int:
        return len(self.queries) + self.db_pings

    def server_timing(self, total_ms: float) -> str:
        entries = [f"{name};dur={ms}" for name, ms in self.spans.items()]
        entries += [
            f'db;dur={round(self.db_query_ms, 2)};desc="{len(self.queries)} queries"',
            f'db-ping;dur={round(self.db_ping_ms, 2)};desc="{self.db_pings} pings"',
            f'db-connect;dur={round(self.db_connect_ms, 2)};desc="{self.db_connects} new"',
            f"other;dur={round(max(total_ms - self.top_level_ms, 0.0), 2)}",
            f"total;dur={total_ms}",
        ]
        return ", ".join(entries)


def current_profile() -> RequestProfile | None:
    return _current.get()


@contextmanager
def timed(name: str) -> Iterator[None]:
    """Record the wall time of the enclosed block under ``name``.

    Wall time, not CPU time: an awaited query inside the block counts, which is
    the point — the span answers "how long did this step make the user wait".
    """
    profile = _current.get()
    if profile is None:
        yield
        return
    profile._depth += 1
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = _ms(time.perf_counter() - start)
        profile._depth -= 1
        profile.add_span(name, elapsed)
        if profile._depth == 0:
            profile.top_level_ms += elapsed


_hooked_engines: set[int] = set()


def install_db_hooks(engine: AsyncEngine) -> None:
    """Attach statement/ping/connect timing to ``engine``. Idempotent.

    SQLAlchemy runs these sync hooks inside its greenlet bridge, which carries
    the calling task's contextvars, so ``_current`` resolves to the request.
    """
    sync_engine = engine.sync_engine
    if id(sync_engine) in _hooked_engines:
        return
    _hooked_engines.add(id(sync_engine))

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_execute(conn, cursor, statement, parameters, context, executemany):
        if _current.get() is not None:
            conn.info.setdefault("_profile_started", []).append(time.perf_counter())

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_execute(conn, cursor, statement, parameters, context, executemany):
        profile = _current.get()
        stack = conn.info.get("_profile_started")
        if profile is None or not stack:
            return
        elapsed = _ms(time.perf_counter() - stack.pop())
        profile.queries.append((_query_label(statement), elapsed))
        profile.db_query_ms += elapsed

    # A new physical connection is a TCP + TLS + Postgres auth handshake —
    # several round trips — so it is tracked apart from queries.
    @event.listens_for(sync_engine, "do_connect")
    def _before_connect(dialect, conn_rec, cargs, cparams):
        profile = _current.get()
        if profile is not None:
            profile._connect_started = time.perf_counter()

    @event.listens_for(sync_engine, "connect")
    def _after_connect(dbapi_connection, connection_record):
        profile = _current.get()
        if profile is None or profile._connect_started is None:
            return
        profile.db_connects += 1
        profile.db_connect_ms += _ms(time.perf_counter() - profile._connect_started)
        profile._connect_started = None

    # pool_pre_ping issues its liveness check straight through the driver, so
    # no cursor event sees it. The pool calls dialect.do_ping on every checkout;
    # wrapping it on this engine's dialect instance is the only way to time it.
    original_ping = sync_engine.dialect.do_ping

    def _timed_ping(dbapi_connection):
        profile = _current.get()
        if profile is None:
            return original_ping(dbapi_connection)
        start = time.perf_counter()
        try:
            return original_ping(dbapi_connection)
        finally:
            profile.db_pings += 1
            profile.db_ping_ms += _ms(time.perf_counter() - start)

    sync_engine.dialect.do_ping = _timed_ping


class ProfilingMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware) so it adds no task hop of its own and
    can stamp ``Server-Timing`` onto the response-start message."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        profile = RequestProfile(
            method=scope["method"],
            path=scope["path"],
            query=scope.get("query_string", b"").decode("latin-1"),
        )
        token = _current.set(profile)
        status: int | None = None
        ttfb_ms: float | None = None
        response_bytes = 0

        async def send_wrapper(message: Message) -> None:
            nonlocal status, ttfb_ms, response_bytes
            if message["type"] == "http.response.start":
                status = message["status"]
                ttfb_ms = profile.elapsed_ms()
                headers = MutableHeaders(scope=message)
                headers.append("Server-Timing", profile.server_timing(ttfb_ms))
                # Without this a cross-origin frontend can't read the header.
                headers.append("Timing-Allow-Origin", "*")
            elif message["type"] == "http.response.body":
                response_bytes += len(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            _current.reset(token)
            total_ms = profile.elapsed_ms()
            logger.info(
                "request.profile",
                method=profile.method,
                path=profile.path,
                query=profile.query,
                status=status,
                total_ms=total_ms,
                ttfb_ms=ttfb_ms,
                response_bytes=response_bytes,
                db_round_trips=profile.db_round_trips,
                db_queries=len(profile.queries),
                db_query_ms=round(profile.db_query_ms, 2),
                db_pings=profile.db_pings,
                db_ping_ms=round(profile.db_ping_ms, 2),
                db_connects=profile.db_connects,
                db_connect_ms=round(profile.db_connect_ms, 2),
                other_ms=round(max((ttfb_ms or total_ms) - profile.top_level_ms, 0.0), 2),
                spans=profile.spans,
                queries=[f"{label} {ms}ms" for label, ms in profile.queries],
            )
