from datetime import date

import pandas as pd

from db import Snapshot, init_db, insert_snapshot, load_all_snapshots


def _make(slug, name="X", total_views=100, rank=1, gender="female", snapshot_date=date(2026, 5, 27)):
    return Snapshot(snapshot_date=snapshot_date, slug=slug, name=name, total_views=total_views, rank=rank, gender=gender)


def test_insert_and_load_round_trip(tmp_path):
    conn = init_db(tmp_path / "test.db")
    insert_snapshot(conn, [
        _make("alice", "Alice", 1_000, 1),
        _make("bob",   "Bob",     900, 2),
    ])
    df = load_all_snapshots(conn)
    assert len(df) == 2
    assert set(df["slug"]) == {"alice", "bob"}
    assert df.loc[df["slug"] == "alice", "total_views"].iloc[0] == 1_000


def test_insert_is_idempotent_per_date_and_slug(tmp_path):
    conn = init_db(tmp_path / "test.db")
    insert_snapshot(conn, [_make("alice", total_views=1_000)])
    insert_snapshot(conn, [_make("alice", total_views=1_500)])
    df = load_all_snapshots(conn)
    assert len(df) == 1
    assert df["total_views"].iloc[0] == 1_500


def test_load_returns_dataframe_with_parsed_dates(tmp_path):
    conn = init_db(tmp_path / "test.db")
    insert_snapshot(conn, [
        _make("a", snapshot_date=date(2026, 5, 26), total_views=10),
        _make("a", snapshot_date=date(2026, 5, 27), total_views=20),
    ])
    df = load_all_snapshots(conn)
    assert pd.api.types.is_datetime64_any_dtype(df["snapshot_date"])
    assert df["snapshot_date"].min().date() == date(2026, 5, 26)


def test_gender_round_trip(tmp_path):
    conn = init_db(tmp_path / "test.db")
    insert_snapshot(conn, [
        _make("alice", gender="female", total_views=1_000),
        _make("johnny", gender="male", total_views=2_000),
    ])
    df = load_all_snapshots(conn)
    assert set(df["gender"]) == {"female", "male"}
    assert df.loc[df["slug"] == "johnny", "gender"].iloc[0] == "male"


def test_migration_adds_gender_to_legacy_db(tmp_path):
    """A DB created by an older schema (no gender column) gets the column added on open."""
    import sqlite3
    db_path = tmp_path / "legacy.db"
    legacy = sqlite3.connect(str(db_path))
    legacy.execute("""
        CREATE TABLE snapshots (
            snapshot_date TEXT NOT NULL,
            slug TEXT NOT NULL,
            name TEXT NOT NULL,
            total_views INTEGER NOT NULL,
            rank INTEGER NOT NULL,
            PRIMARY KEY (snapshot_date, slug)
        )
    """)
    legacy.execute(
        "INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
        ("2026-05-27", "alice", "Alice", 1_000, 1),
    )
    legacy.commit()
    legacy.close()

    # init_db should add the gender column and default existing rows to 'female'.
    conn = init_db(db_path)
    df = load_all_snapshots(conn)
    assert len(df) == 1
    assert df["gender"].iloc[0] == "female"
