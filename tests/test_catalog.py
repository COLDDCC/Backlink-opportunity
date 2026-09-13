from bl import catalog
from bl.db import connect, get_or_create_site


def _seed(conn):
    a = get_or_create_site(conn, "high-dr-directory.com", niche="tools")
    conn.execute(
        "UPDATE sites SET bucket='A', domain_rating=45, is_dofollow=1, "
        "link_format='listing', suitable_for='tools,ai' WHERE id=?",
        (a,),
    )
    b = get_or_create_site(conn, "low-dr-forum.com", niche="tools")
    conn.execute(
        "UPDATE sites SET bucket='B', domain_rating=15, is_dofollow=0, "
        "link_format='profile', suitable_for='general' WHERE id=?",
        (b,),
    )
    c = get_or_create_site(conn, "unrated-guest-post.com", niche="tools")
    conn.execute("UPDATE sites SET bucket='C', link_format='article' WHERE id=?", (c,))
    dead = get_or_create_site(conn, "dead-site.com", niche="tools")
    conn.execute("UPDATE sites SET bucket='stale', domain_rating=80 WHERE id=?", (dead,))
    conn.commit()


def test_list_sites_default_excludes_unusable_buckets(tmp_path):
    conn = connect(str(tmp_path / "cat.db"))
    _seed(conn)
    rows = catalog.list_sites(conn, niche="tools")
    domains = {r["domain"] for r in rows}
    assert "dead-site.com" not in domains  # stale, even with a great DR
    assert domains == {"high-dr-directory.com", "low-dr-forum.com", "unrated-guest-post.com"}


def test_list_sites_dr_range_filter(tmp_path):
    conn = connect(str(tmp_path / "cat.db"))
    _seed(conn)
    rows = catalog.list_sites(conn, niche="tools", min_dr=20, max_dr=50)
    domains = {r["domain"] for r in rows}
    assert domains == {"high-dr-directory.com"}  # unrated site has no DR, excluded by range


def test_list_sites_dofollow_filter(tmp_path):
    conn = connect(str(tmp_path / "cat.db"))
    _seed(conn)
    rows = catalog.list_sites(conn, niche="tools", dofollow="yes")
    assert {r["domain"] for r in rows} == {"high-dr-directory.com"}
    rows = catalog.list_sites(conn, niche="tools", dofollow="no")
    assert {r["domain"] for r in rows} == {"low-dr-forum.com"}


def test_list_sites_link_format_and_suitable_for_filters(tmp_path):
    conn = connect(str(tmp_path / "cat.db"))
    _seed(conn)
    rows = catalog.list_sites(conn, niche="tools", link_format="profile")
    assert {r["domain"] for r in rows} == {"low-dr-forum.com"}

    rows = catalog.list_sites(conn, niche="tools", suitable_for="ai")
    assert {r["domain"] for r in rows} == {"high-dr-directory.com"}


def test_list_sites_orders_unrated_last(tmp_path):
    conn = connect(str(tmp_path / "cat.db"))
    _seed(conn)
    rows = catalog.list_sites(conn, niche="tools")
    domains = [r["domain"] for r in rows]
    assert domains[-1] == "unrated-guest-post.com"  # no DR at all, sorts to the end
