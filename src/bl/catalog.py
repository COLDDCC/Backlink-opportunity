"""Querying the confirmed inventory — `bl list`.

`bl queue` is for triage (what still needs a human decision). This is the
other side: once sites are confirmed, filter the usable ones by DR,
dofollow, link format, etc. — "give me DR 20-50 dofollow directories that
suit tool sites" — separate from the DR/Ahrefs API itself, which phase 1
doesn't touch; domain_rating is whatever a human typed in during `bl
confirm`.
"""
from __future__ import annotations

import sqlite3

READY_BUCKETS = ("A", "B", "C", "D")


def list_sites(
    conn: sqlite3.Connection,
    niche: str | None = None,
    buckets: tuple[str, ...] = READY_BUCKETS,
    min_dr: int | None = None,
    max_dr: int | None = None,
    dofollow: str = "any",  # "yes" / "no" / "any"
    link_format: str | None = None,
    suitable_for: str | None = None,
) -> list[sqlite3.Row]:
    q = "SELECT * FROM sites WHERE 1=1"
    params: list = []
    if niche:
        q += " AND niche = ?"
        params.append(niche)
    if buckets:
        placeholders = ",".join("?" for _ in buckets)
        q += f" AND bucket IN ({placeholders})"
        params.extend(buckets)
    if min_dr is not None:
        q += " AND domain_rating >= ?"
        params.append(min_dr)
    if max_dr is not None:
        q += " AND domain_rating <= ?"
        params.append(max_dr)
    if dofollow == "yes":
        q += " AND is_dofollow = 1"
    elif dofollow == "no":
        q += " AND is_dofollow = 0"
    if link_format:
        q += " AND link_format = ?"
        params.append(link_format)
    if suitable_for:
        q += " AND suitable_for LIKE ?"
        params.append(f"%{suitable_for}%")
    # portable "DR DESC, unknown-DR sites last" without NULLS LAST syntax
    q += " ORDER BY (domain_rating IS NULL), domain_rating DESC, domain ASC"
    return conn.execute(q, params).fetchall()
