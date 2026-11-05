"""The session log. One SQLite file, one events table, append-only. Export to JSON or CSV."""
from __future__ import annotations

import csv
import io
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager

from . import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session TEXT NOT NULL,
  ts REAL NOT NULL,
  kind TEXT NOT NULL,
  sentence_id TEXT,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_events_session ON events(session, ts);
CREATE TABLE IF NOT EXISTS snapshots (
  session TEXT PRIMARY KEY,
  ts REAL NOT NULL,
  doc TEXT NOT NULL
);
"""

@contextmanager
def _db():
    con = sqlite3.connect(config.DB_PATH)
    try:
        con.executescript(_SCHEMA)
        yield con
        con.commit()
    finally:
        con.close()


def _pick_session() -> str:
    """BRACKET_SESSION wins; "new" forces a fresh id. Otherwise resume today's most recent session, so a
    server restart mid-meeting picks up the same draft and log, else start a new one."""
    today = time.strftime("%Y-%m-%d")
    fresh = today + "-" + uuid.uuid4().hex[:4].upper()
    if config.SESSION_ID and config.SESSION_ID.lower() != "new":
        return config.SESSION_ID
    if config.SESSION_ID.lower() == "new":
        return fresh
    with _db() as con:
        row = con.execute("SELECT session FROM snapshots WHERE session LIKE ? ORDER BY ts DESC LIMIT 1", (today + "-%",)).fetchone()
    return row[0] if row else fresh


SESSION = _pick_session()


def log(kind: str, payload: dict, sentence_id: str | None = None) -> None:
    with _db() as con:
        con.execute(
            "INSERT INTO events(session, ts, kind, sentence_id, payload) VALUES (?,?,?,?,?)",
            (SESSION, time.time(), kind, sentence_id, json.dumps(payload, ensure_ascii=False)),
        )


def snapshot(doc: dict) -> None:
    with _db() as con:
        con.execute(
            "INSERT INTO snapshots(session, ts, doc) VALUES (?,?,?) ON CONFLICT(session) DO UPDATE SET ts=excluded.ts, doc=excluded.doc",
            (SESSION, time.time(), json.dumps(doc, ensure_ascii=False)),
        )


def load_snapshot() -> dict | None:
    with _db() as con:
        row = con.execute("SELECT doc FROM snapshots WHERE session=?", (SESSION,)).fetchone()
        return json.loads(row[0]) if row else None


def export(fmt: str = "json") -> tuple[str, str]:
    with _db() as con:
        rows = con.execute("SELECT ts, kind, sentence_id, payload FROM events WHERE session=? ORDER BY ts", (SESSION,)).fetchall()
    if fmt == "csv":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["ts", "kind", "sentence_id", "payload"])
        w.writerows(rows)
        return buf.getvalue(), "text/csv"
    out = [{"ts": r[0], "kind": r[1], "sentence_id": r[2], "payload": json.loads(r[3])} for r in rows]
    return json.dumps({"session": SESSION, "events": out}, ensure_ascii=False, indent=1), "application/json"
