from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class Snapshot:
    snapshot_date: date
    slug: str
    name: str
    total_views: int
    rank: int
    gender: str  # 'female' | 'male'


_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date TEXT NOT NULL,
    slug          TEXT NOT NULL,
    name          TEXT NOT NULL,
    total_views   INTEGER NOT NULL,
    rank          INTEGER NOT NULL,
    gender        TEXT NOT NULL DEFAULT 'female',
    PRIMARY KEY (snapshot_date, slug, gender)
);
"""


def init_db(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute(_SCHEMA)
    # Migration: if the table was created before `gender` existed, add it.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(snapshots)")}
    if "gender" not in cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN gender TEXT NOT NULL DEFAULT 'female'")
    conn.commit()
    return conn


def insert_snapshot(conn: sqlite3.Connection, rows: list[Snapshot]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO snapshots "
        "(snapshot_date, slug, name, total_views, rank, gender) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (r.snapshot_date.isoformat(), r.slug, r.name, r.total_views, r.rank, r.gender)
            for r in rows
        ],
    )
    conn.commit()


def load_all_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT snapshot_date, slug, name, total_views, rank, gender FROM snapshots",
        conn,
    )
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df
