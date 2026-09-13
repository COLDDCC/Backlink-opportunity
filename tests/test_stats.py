from bl import stats as stats_mod
from bl.db import connect, get_or_create_site, now_iso


def _make_db(tmp_path):
    conn = connect(str(tmp_path / "stats.db"))
    s1 = get_or_create_site(conn, "a.com", niche="tools")
    s2 = get_or_create_site(conn, "b.com", niche="tools")
    conn.execute("UPDATE sites SET bucket='A' WHERE id=?", (s1,))
    conn.execute("UPDATE sites SET bucket='D' WHERE id=?", (s2,))
    conn.execute(
        "INSERT INTO attempts (site_id, target_site, submitted_at, status, status_at, time_cost_min) "
        "VALUES (?, 'proivf.com', ?, 'published', ?, 10)",
        (s1, now_iso(), now_iso()),
    )
    conn.execute(
        "INSERT INTO attempts (site_id, target_site, submitted_at, status, status_at, time_cost_min) "
        "VALUES (?, 'proivf.com', ?, 'rejected', ?, 8)",
        (s1, now_iso(), now_iso()),
    )
    conn.commit()
    return conn


def test_bucket_distribution(tmp_path):
    conn = _make_db(tmp_path)
    dist = stats_mod.bucket_distribution(conn, "tools")
    assert dist == {"A": 1, "D": 1}


def test_attempt_stats(tmp_path):
    conn = _make_db(tmp_path)
    result = stats_mod.attempt_stats(conn, "tools")
    assert result["total"] == 2
    assert result["counts"]["published"] == 1
    assert result["counts"]["rejected"] == 1
    assert result["approval_rate"] == 0.5
    assert result["avg_time_cost_min"] == 9.0
    assert result["avg_time_per_published_min"] == 10.0


def test_survival_rate_with_no_eligible_attempts(tmp_path):
    conn = _make_db(tmp_path)
    result = stats_mod.survival_rate_90d(conn, "tools")
    assert result["eligible"] == 0
    assert result["rate"] is None
