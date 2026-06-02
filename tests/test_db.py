from datetime import date

import pandas as pd

from db import Snapshot, init_db, insert_snapshot, load_all_snapshots
from db import insert_category_snapshot, load_all_category_snapshots, CategorySnapshot


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


def test_init_db_creates_category_snapshots_table(tmp_path):
    """init_db creates category_snapshots with the expected schema."""
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(category_snapshots)")}
    assert cols == {"snapshot_date", "category_id", "slug", "name", "video_count", "points"}, \
        f"got cols={cols}"
    pk = [row[1] for row in conn.execute("PRAGMA table_info(category_snapshots)") if row[5] > 0]
    assert set(pk) == {"snapshot_date", "category_id"}, f"got pk cols={pk}"


def test_insert_and_load_category_snapshots_round_trip(tmp_path):
    """insert_category_snapshot + load_all_category_snapshots round-trips correctly."""
    from datetime import date
    conn = init_db(tmp_path / "test.db")
    today = date(2026, 6, 1)
    rows = [
        CategorySnapshot(snapshot_date=today, category_id=37, slug="18-25", name="18-25",
                         video_count=289620, points=65005),
        CategorySnapshot(snapshot_date=today, category_id=29, slug="milf", name="MILF",
                         video_count=199835, points=12500),
        CategorySnapshot(snapshot_date=today, category_id=1, slug="anal", name="Anal",
                         video_count=142217, points=None),  # points may be missing
    ]
    insert_category_snapshot(conn, rows)
    df = load_all_category_snapshots(conn)
    assert len(df) == 3
    assert set(df["category_id"]) == {37, 29, 1}
    milf_row = df[df["category_id"] == 29].iloc[0]
    assert milf_row["name"] == "MILF"
    assert int(milf_row["video_count"]) == 199835
    # Anal had points=None
    anal_row = df[df["category_id"] == 1].iloc[0]
    assert pd.isna(anal_row["points"])


def test_insert_category_snapshot_replaces_on_conflict(tmp_path):
    """Inserting the same (date, id) overwrites — upsert semantics."""
    from datetime import date
    conn = init_db(tmp_path / "test.db")
    today = date(2026, 6, 1)
    v1 = CategorySnapshot(snapshot_date=today, category_id=37, slug="18-25", name="18-25",
                          video_count=100, points=10)
    v2 = CategorySnapshot(snapshot_date=today, category_id=37, slug="18-25", name="18-25",
                          video_count=999, points=99)
    insert_category_snapshot(conn, [v1])
    insert_category_snapshot(conn, [v2])
    df = load_all_category_snapshots(conn)
    assert len(df) == 1
    assert int(df.iloc[0]["video_count"]) == 999


def test_init_db_adds_country_column_migration(tmp_path):
    """init_db creates snapshots with a country column (TEXT, nullable)."""
    db_path = tmp_path / "test.db"
    conn = init_db(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(snapshots)")}
    assert "country" in cols, f"expected 'country' in columns; got {cols}"


def test_insert_and_load_snapshot_with_country(tmp_path):
    """Snapshot.country round-trips through the DB."""
    from datetime import date
    conn = init_db(tmp_path / "test.db")
    insert_snapshot(conn, [
        Snapshot(
            snapshot_date=date(2026, 6, 2), slug="lana-rhoades", name="Lana Rhoades",
            total_views=2_080_000_000, rank=2, gender="female",
            photo_url=None, country="United States",
        ),
        Snapshot(
            snapshot_date=date(2026, 6, 2), slug="eva-elfie", name="Eva Elfie",
            total_views=1_100_000_000, rank=8, gender="female",
            photo_url=None, country=None,  # missing country path
        ),
    ])
    df = load_all_snapshots(conn)
    assert len(df) == 2
    lana = df[df["slug"] == "lana-rhoades"].iloc[0]
    assert lana["country"] == "United States"
    eva = df[df["slug"] == "eva-elfie"].iloc[0]
    assert pd.isna(eva["country"])
