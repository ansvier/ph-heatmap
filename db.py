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
    photo_url: str | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date TEXT NOT NULL,
    slug          TEXT NOT NULL,
    name          TEXT NOT NULL,
    total_views   INTEGER NOT NULL,
    rank          INTEGER NOT NULL,
    gender        TEXT NOT NULL DEFAULT 'female',
    photo_url     TEXT,
    PRIMARY KEY (snapshot_date, slug, gender)
);
"""


def init_db(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute(_SCHEMA)

    # Migration 1: if `gender` column is missing, add it (legacy single-gender table).
    cols = {row[1] for row in conn.execute("PRAGMA table_info(snapshots)")}
    if "gender" not in cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN gender TEXT NOT NULL DEFAULT 'female'")
        conn.commit()
        cols.add("gender")

    # Migration 1b: photo_url column.
    if "photo_url" not in cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN photo_url TEXT")
        conn.commit()

    # Migration 2: if the primary key doesn't include `gender`, rebuild the table.
    # Legacy PK was (snapshot_date, slug); new PK is (snapshot_date, slug, gender)
    # so a slug appearing on both gender top-lists can coexist on the same date.
    pk_cols = [row[1] for row in conn.execute("PRAGMA table_info(snapshots)") if row[5] > 0]
    if pk_cols and "gender" not in pk_cols:
        conn.executescript("""
            CREATE TABLE snapshots_new (
                snapshot_date TEXT NOT NULL,
                slug          TEXT NOT NULL,
                name          TEXT NOT NULL,
                total_views   INTEGER NOT NULL,
                rank          INTEGER NOT NULL,
                gender        TEXT NOT NULL DEFAULT 'female',
                photo_url     TEXT,
                PRIMARY KEY (snapshot_date, slug, gender)
            );
            INSERT OR IGNORE INTO snapshots_new (snapshot_date, slug, name, total_views, rank, gender, photo_url)
            SELECT snapshot_date, slug, name, total_views, rank, gender, photo_url FROM snapshots;
            DROP TABLE snapshots;
            ALTER TABLE snapshots_new RENAME TO snapshots;
        """)
        conn.commit()

    return conn


def insert_snapshot(conn: sqlite3.Connection, rows: list[Snapshot]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO snapshots "
        "(snapshot_date, slug, name, total_views, rank, gender, photo_url) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            (r.snapshot_date.isoformat(), r.slug, r.name, r.total_views, r.rank, r.gender, r.photo_url)
            for r in rows
        ],
    )
    conn.commit()


def load_all_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT snapshot_date, slug, name, total_views, rank, gender, photo_url FROM snapshots",
        conn,
    )
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df
