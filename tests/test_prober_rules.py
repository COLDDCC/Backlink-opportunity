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
