"""Base de données SQLite (matchs et clips)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT UNIQUE NOT NULL,
    court_id TEXT NOT NULL,
    team_a TEXT NOT NULL,
    team_b TEXT NOT NULL,
    format TEXT NOT NULL,
    first_server INTEGER NOT NULL DEFAULT 0,
    points TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    error TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    video_start REAL,
    duration REAL
);
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id INTEGER NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    t REAL NOT NULL,
    status TEXT NOT NULL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.executescript(SCHEMA)
        self._lock = threading.Lock()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[dict]:
        with self._lock:
            return [_row(r) for r in self._conn.execute(sql, params).fetchall()]

    def _one(self, sql: str, params: tuple = ()) -> dict | None:
        rows = self._all(sql, params)
        return rows[0] if rows else None

    # --- réglages ---------------------------------------------------------
    def get_setting(self, key: str) -> str | None:
        row = self._one("SELECT value FROM settings WHERE key = ?", (key,))
        return row["value"] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self._exec(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # --- matchs -----------------------------------------------------------
    def create_match(self, **fields) -> dict:
        fields["format"] = json.dumps(fields["format"])
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = self._exec(f"INSERT INTO matches({cols}) VALUES({marks})", tuple(fields.values()))
        return self.get_match(cur.lastrowid)

    def update_match(self, match_id: int, **fields) -> None:
        if "points" in fields:
            fields["points"] = json.dumps(fields["points"])
        sets = ", ".join(f"{k} = ?" for k in fields)
        self._exec(f"UPDATE matches SET {sets} WHERE id = ?", (*fields.values(), match_id))

    def get_match(self, match_id: int) -> dict | None:
        return self._one("SELECT * FROM matches WHERE id = ?", (match_id,))

    def get_match_by_token(self, token: str) -> dict | None:
        return self._one("SELECT * FROM matches WHERE token = ?", (token,))

    def matches_with_status(self, *statuses: str) -> list[dict]:
        marks = ", ".join("?" for _ in statuses)
        return self._all(f"SELECT * FROM matches WHERE status IN ({marks}) ORDER BY id", statuses)

    def list_matches(self, limit: int = 200) -> list[dict]:
        return self._all("SELECT * FROM matches ORDER BY id DESC LIMIT ?", (limit,))

    def matches_older_than(self, timestamp: float) -> list[dict]:
        return self._all(
            "SELECT * FROM matches WHERE status IN ('done', 'error') AND started_at < ?",
            (timestamp,),
        )

    def delete_match(self, match_id: int) -> None:
        self._exec("DELETE FROM matches WHERE id = ?", (match_id,))

    # --- clips ------------------------------------------------------------
    def create_clip(self, match_id: int, kind: str, t: float, created_at: float) -> dict:
        cur = self._exec(
            "INSERT INTO clips(match_id, kind, t, status, created_at) VALUES(?, ?, ?, 'pending', ?)",
            (match_id, kind, t, created_at),
        )
        return self._one("SELECT * FROM clips WHERE id = ?", (cur.lastrowid,))

    def update_clip(self, clip_id: int, status: str) -> None:
        self._exec("UPDATE clips SET status = ? WHERE id = ?", (status, clip_id))

    def clips_for_match(self, match_id: int) -> list[dict]:
        return self._all("SELECT * FROM clips WHERE match_id = ? ORDER BY id", (match_id,))

    def get_clip(self, clip_id: int) -> dict | None:
        return self._one("SELECT * FROM clips WHERE id = ?", (clip_id,))


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for key in ("format", "points"):
        if key in d and isinstance(d[key], str):
            d[key] = json.loads(d[key])
    return d
