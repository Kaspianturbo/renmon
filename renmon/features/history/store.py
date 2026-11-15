"""SQLite log of readings.

Long term trends are the point: a single soot mass number says little, its
drift over months is what tells you whether the filter is still healthy.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS session (
    id          INTEGER PRIMARY KEY,
    started_at  REAL NOT NULL,
    ecu         TEXT NOT NULL,
    doc         TEXT,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS reading (
    session_id  INTEGER NOT NULL REFERENCES session(id),
    at          REAL NOT NULL,
    code        TEXT NOT NULL,
    value       REAL,
    error       TEXT
);

CREATE INDEX IF NOT EXISTS reading_code_at ON reading(code, at);
CREATE INDEX IF NOT EXISTS reading_session ON reading(session_id);

CREATE TABLE IF NOT EXISTS signal (
    code   TEXT PRIMARY KEY,
    label  TEXT,
    unit   TEXT
);
"""


class Store:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path)
        self.db.executescript(SCHEMA)
        self.db.commit()
        self.session_id: int | None = None

    def start_session(self, ecu: str, doc: str = "", note: str = "") -> int:
        cur = self.db.execute(
            "INSERT INTO session (started_at, ecu, doc, note) VALUES (?, ?, ?, ?)",
            (time.time(), ecu, doc, note),
        )
        self.db.commit()
        self.session_id = cur.lastrowid
        return self.session_id

    def describe(self, signals) -> None:
        self.db.executemany(
            "INSERT INTO signal (code, label, unit) VALUES (?, ?, ?) "
            "ON CONFLICT(code) DO UPDATE SET label=excluded.label, unit=excluded.unit",
            [(s.code, s.label, s.unit) for s in signals],
        )
        self.db.commit()

    def record(self, samples, *, at=None) -> None:
        """samples: iterable of (code, value, error)."""

        if self.session_id is None:
            raise RuntimeError("no session started")
        now = time.time() if at is None else at
        self.db.executemany(
            "INSERT INTO reading (session_id, at, code, value, error) VALUES (?,?,?,?,?)",
            [
                (self.session_id, now, code, value, error)
                for code, value, error in samples
            ],
        )
        self.db.commit()

    def history(self, code: str, limit: int = 200):
        return self.db.execute(
            "SELECT at, value FROM reading WHERE code = ? AND value IS NOT NULL "
            "ORDER BY at DESC LIMIT ?",
            (code, limit),
        ).fetchall()

    def sessions(self):
        return self.db.execute(
            "SELECT s.id, s.started_at, s.ecu, s.note, COUNT(r.rowid) "
            "FROM session s LEFT JOIN reading r ON r.session_id = s.id "
            "GROUP BY s.id ORDER BY s.started_at DESC"
        ).fetchall()

    def close(self) -> None:
        self.db.close()
