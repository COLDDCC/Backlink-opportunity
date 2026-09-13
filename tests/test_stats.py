from datetime import datetime, timedelta, timezone

import pytest

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


def test_turnaround_days_stats(tmp_path):
    conn = connect(str(tmp_path / "turnaround.db"))
    site = get_or_create_site(conn, "slow.com", niche="tools")
    now = datetime.now(timezone.utc)
    # a quick 2-day approval and a much slower 300-day one — the max should
    # surface the slow one even though it's not the average.
    conn.execute(
        "INSERT INTO attempts (site_id, target_site, submitted_at, status, status_at) "
        "VALUES (?, 't.com', ?, 'approved', ?)",
        (site, (now - timedelta(days=2)).isoformat(), now.isoformat()),
    )
    conn.execute(
        "INSERT INTO attempts (site_id, target_site, submitted_at, status, status_at) "
        "VALUES (?, 't.com', ?, 'published', ?)",
        (site, (now - timedelta(days=300)).isoformat(), now.isoformat()),
    )
    # a still-pending submission shouldn't count — there's no outcome yet
    conn.execute(
        "INSERT INTO attempts (site_id, target_site, submitted_at, status, status_at) "
        "VALUES (?, 't.com', ?, 'submitted', ?)",
        (site, now.isoformat(), now.isoformat()),
    )
    conn.commit()

    result = stats_mod.turnaround_days_stats(conn, "tools")
    assert result["n"] == 2
    assert result["max_days"] == pytest.approx(300, abs=0.1)
    assert result["avg_days"] == pytest.approx(151, abs=0.1)
