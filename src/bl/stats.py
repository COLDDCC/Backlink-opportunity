"""`bl stats` aggregation. Pure query + compute functions so they're
testable without going through the CLI.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


def bucket_distribution(conn: sqlite3.Connection, niche: str | None) -> dict[str, int]:
    q = "SELECT bucket, COUNT(*) AS n FROM sites"
    params: list = []
    if niche:
        q += " WHERE niche = ?"
        params.append(niche)
    q += " GROUP BY bucket"
    rows = conn.execute(q, params).fetchall()
    return {(r["bucket"] or "unknown"): r["n"] for r in rows}


def attempt_stats(conn: sqlite3.Connection, niche: str | None) -> dict:
    q = """SELECT a.status, a.time_cost_min FROM attempts a
           JOIN sites s ON s.id = a.site_id"""
    params: list = []
    if niche:
        q += " WHERE s.niche = ?"
        params.append(niche)
    rows = conn.execute(q, params).fetchall()
    total = len(rows)
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    resolved = total - counts.get("submitted", 0) - counts.get("no_response", 0)
    approved_like = counts.get("approved", 0) + counts.get("published", 0)
    approval_rate = (approved_like / resolved) if resolved > 0 else None
    times = [r["time_cost_min"] for r in rows if r["time_cost_min"] is not None]
    avg_time = sum(times) / len(times) if times else None
    published_times = [
        r["time_cost_min"] for r in rows if r["status"] == "published" and r["time_cost_min"] is not None
    ]
    avg_time_per_published = sum(published_times) / len(published_times) if published_times else None
    return {
        "total": total,
        "counts": counts,
        "approval_rate": approval_rate,
        "avg_time_cost_min": avg_time,
        "avg_time_per_published_min": avg_time_per_published,
    }


def survival_rate_90d(conn: sqlite3.Connection, niche: str | None, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=90)).isoformat()
    q = """SELECT a.id AS attempt_id, a.submitted_at FROM attempts a
           JOIN sites s ON s.id = a.site_id
           WHERE a.status = 'published' AND a.submitted_at <= ?"""
    params: list = [cutoff]
    if niche:
        q += " AND s.niche = ?"
        params.append(niche)
    attempts = conn.execute(q, params).fetchall()
    if not attempts:
        return {"eligible": 0, "alive": 0, "rate": None}
    alive = 0
    for a in attempts:
        row = conn.execute(
            "SELECT link_present FROM link_checks WHERE attempt_id = ? ORDER BY checked_at DESC LIMIT 1",
            (a["attempt_id"],),
        ).fetchone()
        if row and row["link_present"]:
            alive += 1
    return {"eligible": len(attempts), "alive": alive, "rate": alive / len(attempts)}
