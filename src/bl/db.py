"""SQLite schema and connection helpers.

Local-first by design: one file, no server, no migrations framework.
Schema follows the spec's data model exactly, plus a small `kv` table
used to remember "last used" values (e.g. last target site) so the
interactive `bl log` flow can default to a single keypress.
"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from urllib.parse import urlparse

DEFAULT_DB_PATH = os.environ.get("BL_DB_PATH", "bl.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS sites (
  id INTEGER PRIMARY KEY,
  domain TEXT UNIQUE NOT NULL,
  niche TEXT,
  channel_type TEXT,
  bucket TEXT,
  bucket_reason TEXT,
  entry_url TEXT,
  needs_register INTEGER,
  captcha_type TEXT,
  is_dofollow INTEGER,
  cost_note TEXT,
  source TEXT,
  first_seen TEXT,
  last_verified TEXT,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS probes (
  id INTEGER PRIMARY KEY,
  site_id INTEGER REFERENCES sites(id),
  probed_at TEXT,
  paths_found TEXT,
  latest_author_post TEXT,
  has_pricing_page INTEGER,
  contact_email_type TEXT,
  marketplace_hit TEXT,
  platform TEXT,
  predicted_bucket TEXT,
  predict_confidence REAL,
  raw TEXT
);

CREATE TABLE IF NOT EXISTS attempts (
  id INTEGER PRIMARY KEY,
  site_id INTEGER REFERENCES sites(id),
  target_site TEXT,
  submitted_at TEXT,
  status TEXT,
  status_at TEXT,
  live_url TEXT,
  time_cost_min INTEGER,
  notes TEXT
);

CREATE TABLE IF NOT EXISTS link_checks (
  id INTEGER PRIMARY KEY,
  attempt_id INTEGER REFERENCES attempts(id),
  checked_at TEXT,
  http_status INTEGER,
  link_present INTEGER,
  rel_attr TEXT,
  indexed INTEGER
);

-- not in the original spec table list; small key/value store so the
-- interactive logger can offer "same as last time" on a single key.
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE INDEX IF NOT EXISTS idx_sites_niche ON sites(niche);
CREATE INDEX IF NOT EXISTS idx_sites_bucket ON sites(bucket);
CREATE INDEX IF NOT EXISTS idx_probes_site ON probes(site_id);
CREATE INDEX IF NOT EXISTS idx_attempts_site ON attempts(site_id);
CREATE INDEX IF NOT EXISTS idx_link_checks_attempt ON link_checks(attempt_id);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or DEFAULT_DB_PATH
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def normalize_domain(raw: str) -> str:
    """Turn a URL or bare domain into a canonical bare domain.

    example.com, https://www.example.com/write-for-us, WWW.Example.com/
    all normalize to "example.com".
    """
    raw = raw.strip()
    if not raw:
        return raw
    if "//" not in raw:
        raw = "//" + raw
    parsed = urlparse(raw)
    host = (parsed.netloc or parsed.path).split("/")[0]
    host = host.split("@")[-1]  # strip userinfo if present
    host = host.split(":")[0]  # strip port
    host = host.lower().strip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def get_or_create_site(
    conn: sqlite3.Connection,
    domain: str,
    niche: str | None = None,
    source: str | None = None,
    channel_type: str | None = None,
) -> int:
    domain = normalize_domain(domain)
    row = conn.execute("SELECT id FROM sites WHERE domain = ?", (domain,)).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        """INSERT INTO sites (domain, niche, channel_type, bucket, source, first_seen)
           VALUES (?, ?, ?, 'unknown', ?, ?)""",
        (domain, niche, channel_type, source, now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def kv_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def kv_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
