from datetime import date

import pandas as pd

from db import Snapshot, init_db, insert_snapshot, load_all_snapshots


def test_insert_and_load_round_trip(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)

    rows = [
        Snapshot(snapshot_date=date(2026, 5, 27), slug="alice", name="Alice", total_views=1_000, rank=1),
        Snapshot(snapshot_date=date(2026, 5, 27), slug="bob",   name="Bob",   total_views=900,   rank=2),
    ]
    insert_snapshot(conn, rows)

    df = load_all_snapshots(conn)
    assert len(df) == 2
    assert set(df["slug"]) == {"alice", "bob"}
    assert df.loc[df["slug"] == "alice", "total_views"].iloc[0] == 1_000


def test_insert_is_idempotent_per_date_and_slug(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)

    row = Snapshot(snapshot_date=date(2026, 5, 27), slug="alice", name="Alice", total_views=1_000, rank=1)
    insert_snapshot(conn, [row])
    # Re-inserting the same (date, slug) replaces the row instead of erroring.
    updated = Snapshot(snapshot_date=date(2026, 5, 27), slug="alice", name="Alice", total_views=1_500, rank=1)
    insert_snapshot(conn, [updated])

    df = load_all_snapshots(conn)
    assert len(df) == 1
    assert df["total_views"].iloc[0] == 1_500


def test_load_returns_dataframe_with_parsed_dates(tmp_path):
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)

    insert_snapshot(conn, [
        Snapshot(snapshot_date=date(2026, 5, 26), slug="a", name="A", total_views=10, rank=1),
        Snapshot(snapshot_date=date(2026, 5, 27), slug="a", name="A", total_views=20, rank=1),
    ])

    df = load_all_snapshots(conn)
    assert pd.api.types.is_datetime64_any_dtype(df["snapshot_date"])
    assert df["snapshot_date"].min().date() == date(2026, 5, 26)
