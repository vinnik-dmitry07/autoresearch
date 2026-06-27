'''EvolutionDB (Phase 2): searchable history index over the append-only archive.

Uses SQLite FTS5 when available (full-text search over candidate reasons/diffs/notes),
falling back to a LIKE scan otherwise. The DB is a *derived read model* rebuilt from the
durable JSON archive - it is never the source of truth, so losing it is harmless.
'''
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass
class HistoryHit:
    candidate_id: str
    status: str
    content: str


def _has_fts5(conn: sqlite3.Connection) -> bool:
    try:
        conn.execute('CREATE VIRTUAL TABLE _fts_probe USING fts5(x)')
        conn.execute('DROP TABLE _fts_probe')
        return True
    except sqlite3.OperationalError:
        return False


class EvolutionDB:
    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.fts = _has_fts5(self.conn)
        if self.fts:
            self.conn.execute(
                'CREATE VIRTUAL TABLE IF NOT EXISTS history '
                'USING fts5(candidate_id, status, content)'
            )
        else:
            self.conn.execute(
                'CREATE TABLE IF NOT EXISTS history '
                '(candidate_id TEXT, status TEXT, content TEXT)'
            )
        self.conn.commit()

    def index(self, candidate_id: str, status: str, content: str) -> None:
        self.conn.execute(
            'INSERT INTO history (candidate_id, status, content) VALUES (?, ?, ?)',
            (candidate_id, status, content),
        )
        self.conn.commit()

    def search(self, query: str, limit: int = 20) -> list[HistoryHit]:
        if self.fts:
            rows = self.conn.execute(
                'SELECT candidate_id, status, content FROM history '
                'WHERE history MATCH ? LIMIT ?',
                (query, limit),
            ).fetchall()
        else:
            rows = self.conn.execute(
                'SELECT candidate_id, status, content FROM history '
                'WHERE content LIKE ? LIMIT ?',
                (f'%{query}%', limit),
            ).fetchall()
        return [HistoryHit(*row) for row in rows]

    def close(self) -> None:
        self.conn.close()
