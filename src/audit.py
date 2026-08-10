"""Audit log — who changed what, when.

Several people can now edit classes, grades and rosters, all through the same
shared code. Without a log, "who cancelled that class?" or "who dropped that
dealer?" has no answer, and a wrong edit is indistinguishable from a bug.

Every mutation writes one append-only row here. It is deliberately dumb and
separate from the thing being changed:

  - append-only: entries are never updated or deleted by app code
  - never raises: a logging failure must not fail the user's action
  - self-contained: its own table, so a catalog rebuild can't wipe history

Stored in the same SQLite file as registrations (data/registrations.db), which
already lives on the persistent disk and is included in any backup of it.
"""
import json
import sqlite3
from datetime import datetime

from config import DB_PATH

_DDL = """
CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  at         TEXT NOT NULL,      -- ISO timestamp
  actor      TEXT NOT NULL,      -- which hub mode acted (admin / fsr / public)
  action     TEXT NOT NULL,      -- class.update, class.create, registration.remove, ...
  target     TEXT,               -- event_id or registration id
  detail     TEXT,               -- JSON: the before -> after of what changed
  ip         TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_target ON audit_log(target);
CREATE INDEX IF NOT EXISTS idx_audit_at ON audit_log(at);
"""


def _con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.executescript(_DDL)
    return con


def log(actor, action, target="", detail=None, ip=""):
    """Record one change. Never raises — auditing must not break the action."""
    try:
        con = _con()
        con.execute(
            "INSERT INTO audit_log (at, actor, action, target, detail, ip) VALUES (?,?,?,?,?,?)",
            (datetime.now().isoformat(timespec="seconds"), str(actor or "unknown"),
             str(action), str(target or ""),
             json.dumps(detail, default=str) if detail is not None else None, str(ip or "")))
        con.commit()
        con.close()
    except Exception:  # noqa: BLE001 - logging is never allowed to fail a write
        pass


def recent(limit=100, target=""):
    """Newest entries first — for 'what happened to this class?'."""
    try:
        con = _con()
        if target:
            rows = con.execute(
                "SELECT * FROM audit_log WHERE target = ? ORDER BY id DESC LIMIT ?",
                (target, limit)).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            if d.get("detail"):
                try:
                    d["detail"] = json.loads(d["detail"])
                except ValueError:
                    pass
            out.append(d)
        con.close()
        return out
    except Exception:  # noqa: BLE001
        return []
