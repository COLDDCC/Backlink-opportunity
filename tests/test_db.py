import sqlite3

from bl.db import connect, get_or_create_site, normalize_domain


def test_normalize_domain_variants():
    assert normalize_domain("example.com") == "example.com"
    assert normalize_domain("https://www.example.com/write-for-us") == "example.com"
    assert normalize_domain("WWW.Example.com/") == "example.com"
    assert normalize_domain("http://example.com:8080/path") == "example.com"
    assert normalize_domain("  example.com  ") == "example.com"


def test_get_or_create_site_is_idempotent(tmp_path):
    conn = connect(str(tmp_path / "test.db"))
    id1 = get_or_create_site(conn, "example.com", niche="tools", source="unit-test")
    id2 = get_or_create_site(conn, "https://www.example.com/", niche="tools")
    assert id1 == id2
    row = conn.execute("SELECT * FROM sites WHERE id = ?", (id1,)).fetchone()
    assert row["domain"] == "example.com"
    assert row["bucket"] == "unknown"
    assert row["source"] == "unit-test"


def test_migration_adds_new_columns_to_pre_existing_db(tmp_path):
    """Simulate a bl.db created before suitable_for/expected_wait existed —
    connect() must backfill the columns without losing existing rows."""
    path = str(tmp_path / "old.db")
    old_conn = sqlite3.connect(path)
    old_conn.execute(
        """CREATE TABLE sites (
            id INTEGER PRIMARY KEY, domain TEXT UNIQUE NOT NULL, niche TEXT,
            channel_type TEXT, bucket TEXT, bucket_reason TEXT, entry_url TEXT,
            needs_register INTEGER, captcha_type TEXT, is_dofollow INTEGER,
            cost_note TEXT, source TEXT, first_seen TEXT, last_verified TEXT, notes TEXT
        )"""
    )
    old_conn.execute("INSERT INTO sites (domain, bucket) VALUES ('legacy.com', 'A')")
    old_conn.commit()
    old_conn.close()

    conn = connect(path)
    row = conn.execute("SELECT * FROM sites WHERE domain = 'legacy.com'").fetchone()
    assert row["bucket"] == "A"
    assert row["suitable_for"] is None
    assert row["expected_wait"] is None
