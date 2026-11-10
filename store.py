"""Vision Sentry event store — SQLite via Hermes' plugin_db."""
import datetime
import json
import sqlite3

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    cam TEXT,
    kind TEXT,
    summary TEXT,
    confidence REAL,
    snapshot TEXT,
    extra TEXT
);
CREATE INDEX IF NOT EXISTS events_ts ON events (ts DESC);
"""


def _conn():
    from plugins.plugin_storage import plugin_db
    conn = plugin_db("vision-sentry")
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _parse_since(since):
    """Best-effort '2 hours ago' / ISO / date parsing. Returns ISO string or None."""
    if not since:
        return None
    s = str(since).strip().lower()
    try:
        if s.endswith(" ago"):
            num, unit = s[:-4].strip().split(" ")[-2:]
            n = float(num)
            delta = {"s": 1, "sec": 1, "secs": 1, "second": 1, "seconds": 1,
                     "m": 60, "min": 60, "mins": 60, "minute": 60, "minutes": 60,
                     "h": 3600, "hr": 3600, "hrs": 3600, "hour": 3600, "hours": 3600,
                     "d": 86400, "day": 86400, "days": 86400,
                     "w": 604800, "week": 604800, "weeks": 604800}.get(unit)
            if delta:
                return (datetime.datetime.now().astimezone()
                        - datetime.timedelta(seconds=n * delta)).isoformat(timespec="seconds")
        dt = datetime.datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt.isoformat(timespec="seconds")
    except Exception:
        return None


def add_event(cam="", kind="", summary="", confidence=None, snapshot="", extra=None) -> int:
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO events (ts, cam, kind, summary, confidence, snapshot, extra) "
        "VALUES (?,?,?,?,?,?,?)",
        (_now(), cam, kind, summary, confidence, snapshot,
         json.dumps(extra) if extra else None),
    )
    conn.commit()
    return int(cur.lastrowid or 0)


def list_events(limit=10, kind=None, since=None) -> list[dict]:
    limit = max(1, min(int(limit or 10), 50))
    sql = "SELECT id, ts, cam, kind, summary, confidence, snapshot, extra FROM events"
    clauses, params = [], []
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    since_iso = _parse_since(since)
    if since_iso:
        clauses.append("ts >= ?")
        params.append(since_iso)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY ts DESC LIMIT ?"
    params.append(limit)
    rows = _conn().execute(sql, params).fetchall()
    out = []
    for r in rows:
        d = dict(zip(["id", "ts", "cam", "kind", "summary", "confidence", "snapshot", "extra"], r))
        if d.get("extra"):
            try:
                d["extra"] = json.loads(d["extra"])
            except Exception:
                pass
        out.append(d)
    return out


def latest_snapshot() -> str:
    row = _conn().execute(
        "SELECT snapshot FROM events WHERE snapshot != '' ORDER BY ts DESC LIMIT 1"
    ).fetchone()
    return row[0] if row else ""


def count() -> int:
    return _conn().execute("SELECT COUNT(*) FROM events").fetchone()[0]
