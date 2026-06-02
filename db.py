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
    country: str | None = None


@dataclass(frozen=True)
class CategorySnapshot:
    snapshot_date: date
    category_id: int
    slug: str
    name: str
    video_count: int
    points: int | None = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_date TEXT NOT NULL,
    slug          TEXT NOT NULL,
    name          TEXT NOT NULL,
    total_views   INTEGER NOT NULL,
    rank          INTEGER NOT NULL,
    gender        TEXT NOT NULL DEFAULT 'female',
    photo_url     TEXT,
    country       TEXT,
    PRIMARY KEY (snapshot_date, slug, gender)
);
"""


_CATEGORY_SNAPSHOTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS category_snapshots (
    snapshot_date  TEXT    NOT NULL,
    category_id    INTEGER NOT NULL,
    slug           TEXT    NOT NULL,
    name           TEXT    NOT NULL,
    video_count    INTEGER NOT NULL,
    points         INTEGER,
    PRIMARY KEY (snapshot_date, category_id)
);
CREATE INDEX IF NOT EXISTS idx_cs_date     ON category_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS idx_cs_category ON category_snapshots(category_id);
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
        cols.add("photo_url")

    # Migration 1c: country column.
    if "country" not in cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN country TEXT")
        conn.commit()
        cols.add("country")

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
                country       TEXT,
                PRIMARY KEY (snapshot_date, slug, gender)
            );
            INSERT OR IGNORE INTO snapshots_new (snapshot_date, slug, name, total_views, rank, gender, photo_url, country)
            SELECT snapshot_date, slug, name, total_views, rank, gender, photo_url, country FROM snapshots;
            DROP TABLE snapshots;
            ALTER TABLE snapshots_new RENAME TO snapshots;
        """)
        conn.commit()

    conn.executescript(_CATEGORY_SNAPSHOTS_SCHEMA)
    conn.commit()

    return conn


def insert_snapshot(conn: sqlite3.Connection, rows: list[Snapshot]) -> None:
    conn.executemany(
        "INSERT OR REPLACE INTO snapshots "
        "(snapshot_date, slug, name, total_views, rank, gender, photo_url, country) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (r.snapshot_date.isoformat(), r.slug, r.name, r.total_views, r.rank,
             r.gender, r.photo_url, r.country)
            for r in rows
        ],
    )
    conn.commit()


def load_all_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql_query(
        "SELECT snapshot_date, slug, name, total_views, rank, gender, photo_url, country FROM snapshots",
        conn,
    )
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df


def insert_category_snapshot(conn: sqlite3.Connection, rows: list[CategorySnapshot]) -> None:
    """Upsert category snapshot rows. PK is (snapshot_date, category_id)."""
    conn.executemany(
        "INSERT OR REPLACE INTO category_snapshots "
        "(snapshot_date, category_id, slug, name, video_count, points) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (r.snapshot_date.isoformat(), r.category_id, r.slug, r.name, r.video_count, r.points)
            for r in rows
        ],
    )
    conn.commit()


def load_all_category_snapshots(conn: sqlite3.Connection) -> pd.DataFrame:
    """Load the full category_snapshots table as a DataFrame."""
    df = pd.read_sql_query(
        "SELECT snapshot_date, category_id, slug, name, video_count, points "
        "FROM category_snapshots",
        conn,
    )
    if not df.empty:
        df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])
    return df
