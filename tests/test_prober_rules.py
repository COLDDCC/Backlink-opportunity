from datetime import datetime, timedelta, timezone

from bl.prober import (
    BIZ_EMAIL_PREFIXES,
    FEE_KEYWORD_RE,
    QUEUE_KEYWORD_RE,
    _activity_tendency,
    probe_site,
)


def test_fee_keyword_regex_hits():
    assert FEE_KEYWORD_RE.search("We charge a $50 processing fee per post.")
    assert FEE_KEYWORD_RE.search("This is a paid guest post service.")
    assert not FEE_KEYWORD_RE.search("Submit your free guest post today, no cost at all.")


def test_biz_email_prefixes():
    assert "seo@example.com".startswith(BIZ_EMAIL_PREFIXES)
    assert "partnerships@example.com".startswith(BIZ_EMAIL_PREFIXES)
    assert not "editor@example.com".startswith(BIZ_EMAIL_PREFIXES)


def test_queue_keyword_regex():
    assert QUEUE_KEYWORD_RE.search("Our editorial calendar is booked, please allow 4-6 weeks.")
    assert not QUEUE_KEYWORD_RE.search("Submit today and we'll publish within 24 hours.")


def test_activity_tendency_thresholds():
    today = datetime.now(timezone.utc).date()
    assert _activity_tendency((today - timedelta(days=5)).isoformat()) == "fresh"
    assert _activity_tendency((today - timedelta(days=100)).isoformat()) == "aging"
    assert _activity_tendency((today - timedelta(days=300)).isoformat()) == "stale"
    assert _activity_tendency(None) == "stale"


def test_probe_site_detects_commercial_page_as_d(fixture_server):
    fixture_server.routes["/"] = (200, "<html>homepage</html>")
    fixture_server.routes["/advertise"] = (200, "<html>advertise with us</html>")
    result = probe_site("fixture.test", base_url=fixture_server.base_url)
    assert result.predicted_bucket == "D"
    assert "商业化" in result.bucket_reason


def test_probe_site_detects_fee_keyword_as_d(fixture_server):
    fixture_server.routes["/"] = (200, "<html>homepage</html>")
    fixture_server.routes["/write-for-us"] = (200, "<html>We charge a $99 processing fee per article.</html>")
    result = probe_site("fixture.test", base_url=fixture_server.base_url)
    assert result.predicted_bucket == "D"


def test_probe_site_fresh_forum_predicts_a(fixture_server):
    now_str = datetime.now(timezone.utc).date().isoformat()
    fixture_server.routes["/"] = (200, '<html><meta name="generator" content="Discourse"></html>')
    fixture_server.routes["/register"] = (200, "<html>join us</html>")
    fixture_server.routes["/sitemap.xml"] = (
        200,
        f"<urlset><url><loc>https://fixture.test/author/joe</loc><lastmod>{now_str}</lastmod></url></urlset>",
    )
    result = probe_site("fixture.test", base_url=fixture_server.base_url)
    assert result.platform == "discourse"
    assert result.predicted_bucket == "A"


def test_probe_site_no_activity_is_stale(fixture_server):
    fixture_server.routes["/"] = (200, "<html>a very quiet website</html>")
    result = probe_site("fixture.test", base_url=fixture_server.base_url)
    assert result.predicted_bucket == "stale"


def test_probe_site_blocked_homepage_short_circuits(fixture_server):
    fixture_server.routes["/"] = (403, "blocked by WAF")
    result = probe_site("fixture.test", base_url=fixture_server.base_url)
    assert result.predicted_bucket == "unknown"
    assert result.raw.get("blocked") is True
    # the whole point: no path probing happened after the 403
    assert result.paths_found == {}


def test_probe_site_distinguishes_egress_policy_block_from_real_waf(fixture_server):
    fixture_server.routes["/"] = (
        403, "Host not in allowlist: fixture.test. Add this host to your network egress settings to allow access.",
    )
    result = probe_site("fixture.test", base_url=fixture_server.base_url)
    assert result.raw.get("network_policy_blocked") is True
    assert "出网白名单" in result.bucket_reason
    assert "Cloudflare" not in result.bucket_reason  # don't blame the site for our own sandbox's policy


def test_probe_site_unreachable_short_circuits(fixture_server):
    base_url = fixture_server.base_url
    fixture_server.stop()  # port is now closed -> connection refused
    result = probe_site("fixture.test", base_url=base_url)
    assert result.predicted_bucket == "unknown"
    assert result.raw.get("blocked") is True
    assert result.paths_found == {}


def test_probe_site_force_bypasses_short_circuit(fixture_server):
    fixture_server.routes["/"] = (403, "blocked by WAF")
    result = probe_site("fixture.test", base_url=fixture_server.base_url, force=True)
    assert result.raw.get("blocked") is not True
    assert result.paths_found  # path probing actually ran


def test_probe_site_follows_sitemap_index_to_post_sitemap(fixture_server):
    now_str = datetime.now(timezone.utc).date().isoformat()
    base = fixture_server.base_url
    fixture_server.routes["/"] = (200, "<html>a wordpress-shaped blog</html>")
    fixture_server.routes["/write-for-us"] = (200, "<html>send us your post</html>")
    fixture_server.routes["/sitemap.xml"] = (
        200,
        f"<sitemapindex>"
        f"<sitemap><loc>{base}/page-sitemap.xml</loc></sitemap>"
        f"<sitemap><loc>{base}/post-sitemap.xml</loc></sitemap>"
        f"</sitemapindex>",
    )
    fixture_server.routes["/post-sitemap.xml"] = (
        200,
        f"<urlset><url><loc>{base}/2024/some-guest-post</loc><lastmod>{now_str}</lastmod></url></urlset>",
    )
    result = probe_site("fixture.test", base_url=base)
    assert result.latest_author_post == now_str
    assert result.predicted_bucket in ("A", "B")
