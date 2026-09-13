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
