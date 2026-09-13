"""The prober: given a domain, produce a predicted bucket + evidence.

Implements spec section 5. Rules, in order:

1. D-signals (any one hit -> bucket D immediately, stop probing further).
2. Queue signals (bias toward C).
3. Activity signal (latest guest-authored post date) -> the real decider
   between A/B/C/stale, because it's evidence of outcome, not a policy
   page's self-description.
4. Platform fingerprint (forum software tends to mean "register and post").

网络请求要求：自定义 UA、10s 超时、失败重试一次、结果落库不抛异常中断批次。
不做验证码/反爬绕过 —— 遇到 403/Cloudflare 只如实记录状态码。
"""
from __future__ import annotations

import concurrent.futures
import json
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

USER_AGENT = "BacklinkOpportunityBot/0.1 (+research; contact: see repo README)"
TIMEOUT = 10
RETRIES = 1

# --- 5.5 路径探测清单 -------------------------------------------------

ENTRY_PATHS = [
    "/write-for-us", "/write-for-us/", "/writeforus",
    "/guest-post", "/guest-posts", "/guest-posting", "/guest-blogging",
    "/contribute", "/contributors", "/contribution-guidelines",
    "/submit", "/submit-post", "/submit-article", "/submit-url", "/submit-link", "/submit-tool",
    "/add-url", "/add-listing", "/add-your-site", "/add-tool",
    "/become-a-contributor", "/editorial-guidelines", "/submission-guidelines",
]
COMMERCIAL_PATHS = ["/advertise", "/advertising", "/pricing", "/sponsored", "/sponsored-post", "/media-kit"]
MISC_PATHS = ["/register", "/signup", "/join"]
ALL_PATHS = ENTRY_PATHS + COMMERCIAL_PATHS + MISC_PATHS

# --- 5.1 D 信号 ---------------------------------------------------------

FEE_KEYWORD_RE = re.compile(
    r"contribution fee|processing fee|we charge|paid guest post|\$\s?\d+.{0,30}(post|article)|(post|article).{0,30}\$\s?\d+",
    re.IGNORECASE,
)
BIZ_EMAIL_PREFIXES = ("seo@", "partnerships@", "marketing@", "sales@", "bd@")
EMAIL_RE = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")

# --- 5.2 排队信号 -------------------------------------------------------

QUEUE_KEYWORD_RE = re.compile(
    r"editorial calendar|plan(?:ned)? content (?:for )?3 months|allow 4-6 weeks|"
    r"currently at capacity|writing sample|previously published|"
    r"submit(?:ting)? (?:an )?outline|minimum(?: of)? 1500|1500\+? words|exclusive(?:ly)? original",
    re.IGNORECASE,
)
PORTFOLIO_RE = re.compile(r"portfolio", re.IGNORECASE)

# --- 5.4 平台指纹 --------------------------------------------------------

PLATFORM_SIGNATURES = [
    ("wordpress", re.compile(r"wp-content|wp-includes|wp-json", re.IGNORECASE)),
    ("discourse", re.compile(
        r"discourse[- ]?(cdn|hosted)|powered by discourse|Docker/Discourse|"
        r'name="generator"\s+content="discourse',
        re.IGNORECASE,
    )),
    ("phpbb", re.compile(r"powered by phpbb|phpbb\.com", re.IGNORECASE)),
    ("xenforo", re.compile(r"xenforo|data-xf-init", re.IGNORECASE)),
    ("ghost", re.compile(r'name="generator"\s+content="ghost', re.IGNORECASE)),
]
FORUM_PLATFORMS = {"discourse", "phpbb", "xenforo"}

DATE_PATTERNS = [
    re.compile(r"<lastmod>([\dT:+\-.Z]{10,25})</lastmod>", re.IGNORECASE),
    re.compile(r"\b(\d{4}-\d{2}-\d{2})\b"),
]
MONTH_NAME_RE = re.compile(
    r"\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
    r"Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?\s+(\d{1,2}),?\s+(\d{4})\b"
)

DEFAULT_BLACKLIST_PATH = Path("data/marketplace_domains.txt")
# fallback for when `bl` is run from outside the repo root (installed package)
PACKAGE_BLACKLIST_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "marketplace_domains.txt"

# home page statuses that mean "don't bother probing further paths" — either
# the domain is unreachable, or it's actively blocking us (Cloudflare/WAF).
# Per spec: record honestly, don't try to work around it.
BLOCKED_HOME_STATUSES = {403, 429, 503}


def _load_marketplace_blacklist(path: Path | None = None) -> set[str]:
    import os

    candidates = [
        Path(os.environ["BL_MARKETPLACE_BLACKLIST"]) if os.environ.get("BL_MARKETPLACE_BLACKLIST") else None,
        path,
        DEFAULT_BLACKLIST_PATH,
        PACKAGE_BLACKLIST_PATH,
    ]
    path = next((p for p in candidates if p is not None and p.exists()), None)
    if path is None:
        return set()
    domains = set()
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip().lower()
        if line and not line.startswith("#"):
            domains.add(line)
    return domains


@dataclass
class ProbeResult:
    domain: str
    paths_found: dict = field(default_factory=dict)
    latest_author_post: Optional[str] = None
    has_pricing_page: bool = False
    contact_email_type: str = "unknown"
    marketplace_hit: Optional[str] = None
    platform: str = "unknown"
    predicted_bucket: str = "unknown"
    predict_confidence: float = 0.0
    bucket_reason: str = ""
    entry_url: Optional[str] = None
    raw: dict = field(default_factory=dict)


def _fetch(session: requests.Session, url: str, method: str = "GET") -> Optional[requests.Response]:
    """GET/HEAD with one retry. Never raises — returns None on total failure."""
    for attempt in range(RETRIES + 1):
        try:
            resp = session.request(
                method, url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT},
                allow_redirects=True,
            )
            return resp
        except requests.RequestException:
            if attempt == RETRIES:
                return None
            continue
    return None


def _probe_path(session: requests.Session, base: str, path: str, use_head: bool) -> tuple[str, int | str]:
    url = base + path
    resp = _fetch(session, url, method="HEAD" if use_head else "GET")
    if resp is None:
        return path, "ERR"
    if use_head and resp.status_code == 405:
        resp = _fetch(session, url, method="GET")
        if resp is None:
            return path, "ERR"
    return path, resp.status_code


def _extract_dates(text: str) -> list[datetime]:
    found = []
    for pat in DATE_PATTERNS:
        for m in pat.finditer(text):
            raw = m.group(1)
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d"):
                try:
                    d = datetime.strptime(raw[:19] if "T" in raw else raw[:10], fmt.replace("%z", ""))
                    found.append(d.replace(tzinfo=timezone.utc))
                    break
                except ValueError:
                    continue
    for m in MONTH_NAME_RE.finditer(text):
        month_str, day_str, year_str = m.groups()
        try:
            d = datetime.strptime(f"{month_str} {day_str} {year_str}", "%b %d %Y")
        except ValueError:
            try:
                d = datetime.strptime(f"{month_str} {day_str} {year_str}", "%B %d %Y")
            except ValueError:
                continue
        found.append(d.replace(tzinfo=timezone.utc))
    return found


SUB_SITEMAP_RE = re.compile(r"(post|article|blog)[-_]?sitemap|sitemap[-_]?(post|article|blog)", re.IGNORECASE)


def _detect_activity(session: requests.Session, base: str) -> Optional[str]:
    """Best-effort latest guest-authored post date.

    Phase 1 has no search-engine API, so we approximate `site:domain
    inurl:author/` with three falling-back layers:

    1. A flat sitemap.xml with per-URL <lastmod>, filtered to URLs that
       look like author/contributor/blog pages (most precise when present).
    2. A sitemap INDEX (the common WordPress/Yoast shape: sitemap.xml just
       lists post-sitemap.xml, page-sitemap.xml, ...) — follow up to 2
       sub-sitemaps whose filename suggests posts/articles/blog and take
       the max <lastmod> across their entries. Less precise (it proves
       "site is still publishing", not "still publishing GUEST posts")
       but layer 1 alone misses this very common sitemap shape entirely.
    3. A plain scan of /author, /contributors, /blog for visible dates.

    This is a heuristic, not ground truth — human queue review is the
    final check.
    """
    candidates: list[datetime] = []
    sitemap_entries: list[tuple[str, str]] = []
    for sitemap_path in ("/sitemap.xml", "/sitemap_index.xml"):
        resp = _fetch(session, base + sitemap_path)
        if resp is None or resp.status_code != 200:
            continue
        sitemap_entries = re.findall(
            r"<loc>([^<]+)</loc>\s*(?:<lastmod>([^<]+)</lastmod>)?", resp.text, re.IGNORECASE
        )
        if sitemap_entries:
            break

    for loc, lastmod in sitemap_entries:
        if lastmod and re.search(r"author|contributor|/blog/", loc, re.IGNORECASE):
            candidates.extend(_extract_dates(f"<lastmod>{lastmod}</lastmod>"))

    if not candidates and sitemap_entries:
        sub_sitemaps = [loc for loc, _ in sitemap_entries if SUB_SITEMAP_RE.search(loc)]
        for sub_url in sub_sitemaps[:2]:
            resp = _fetch(session, sub_url)
            if resp is None or resp.status_code != 200:
                continue
            for m in re.finditer(r"<lastmod>([^<]+)</lastmod>", resp.text, re.IGNORECASE):
                candidates.extend(_extract_dates(f"<lastmod>{m.group(1)}</lastmod>"))

    if not candidates:
        for listing_path in ("/author", "/contributors", "/blog"):
            resp = _fetch(session, base + listing_path)
            if resp is None or resp.status_code != 200:
                continue
            candidates.extend(_extract_dates(resp.text))
    if not candidates:
        return None
    return max(candidates).date().isoformat()


def _activity_tendency(latest_author_post: Optional[str]) -> str:
    if not latest_author_post:
        return "stale"
    try:
        latest = datetime.fromisoformat(latest_author_post).replace(tzinfo=timezone.utc)
    except ValueError:
        return "stale"
    days = (datetime.now(timezone.utc) - latest).days
    if days <= 30:
        return "fresh"
    if days <= 180:
        return "aging"
    return "stale"


def _looks_like_egress_policy_block(resp: requests.Response) -> bool:
    """Detect a restricted-egress sandbox's own denial page, as opposed to
    a real response from the target site. Anthropic's Claude Code remote
    environments (and similar CI/agent sandboxes) proxy all outbound HTTPS
    and, for a host not on their allowlist, hand back a same-shaped 403
    with this exact body instead of ever reaching the real site."""
    if resp.status_code != 403:
        return False
    body = resp.text or ""
    return len(body) < 500 and "not in allowlist" in body.lower()


def probe_site(
    domain: str,
    blacklist: Optional[set[str]] = None,
    session: Optional[requests.Session] = None,
    base_url: Optional[str] = None,
    force: bool = False,
) -> ProbeResult:
    """`base_url` overrides the https://{domain} guess — used by tests to
    point the prober at a local fixture server instead of the real internet.

    `force` skips the "homepage unreachable/blocked -> stop early" short
    circuit, for the rare manual re-check of a domain you have reason to
    believe works despite a bad homepage response.
    """
    result = ProbeResult(domain=domain)
    blacklist = blacklist if blacklist is not None else _load_marketplace_blacklist()
    own_session = session is None
    session = session or requests.Session()
    try:
        if base_url is not None:
            base = base_url
            home = _fetch(session, base)
        else:
            base = f"https://{domain}"
            home = _fetch(session, base)
            if home is None:
                base = f"http://{domain}"
                home = _fetch(session, base)
        home_text = home.text if home is not None else ""
        home_status = home.status_code if home is not None else "ERR"
        result.raw["home_status"] = home_status

        # Domain unreachable or actively blocking us — record honestly and
        # stop. Don't burn ~20s * 26 paths finding out the same thing 26
        # times; that's what let one dead domain blow the "200 domains in
        # 10 minutes" budget for the whole batch.
        if not force and (home is None or home_status in BLOCKED_HOME_STATUSES):
            result.predicted_bucket = "unknown"
            result.raw["blocked"] = True
            if home is None:
                result.bucket_reason = "域名无法访问（DNS/连接失败/超时），未做进一步探测，需人工检查"
            elif _looks_like_egress_policy_block(home):
                # Claude Code sandboxes (and similar restricted-egress
                # environments) return their own synthetic 403 for any host
                # not on the network allowlist — that's OUR outbound policy
                # denying the request, not the target site's Cloudflare/WAF.
                # Mislabeling this as "site blocks us" would be actively
                # wrong data going into the bucket. Say what actually happened.
                result.bucket_reason = (
                    "当前运行环境的出网白名单拦截了这个域名（不是目标网站本身的响应），"
                    "需要在开放出网的环境下重新探测才能得出真实判断"
                )
                result.raw["network_policy_blocked"] = True
            else:
                result.bucket_reason = f"首页返回 {home_status}（可能是 Cloudflare/WAF 拦截），如实记录，未做绕过"
            result.predict_confidence = 0.2
            return result

        # path probing
        for path in ALL_PATHS:
            use_head = path in COMMERCIAL_PATHS
            p, status = _probe_path(session, base, path, use_head)
            result.paths_found[p] = status

        # entry_url guess: first live entry-style path
        for p in ENTRY_PATHS:
            if result.paths_found.get(p) == 200:
                result.entry_url = base + p
                break

        entry_text = ""
        if result.entry_url:
            resp = _fetch(session, result.entry_url)
            if resp is not None and resp.status_code == 200:
                entry_text = resp.text
        combined_text = home_text + "\n" + entry_text

        # --- D signals, short-circuit ---
        result.has_pricing_page = any(result.paths_found.get(p) == 200 for p in COMMERCIAL_PATHS)
        if result.has_pricing_page:
            result.predicted_bucket = "D"
            result.bucket_reason = "存在商业化页面 (/advertise /pricing /sponsored 等返回 200)"
            result.predict_confidence = 0.8
            return result

        if FEE_KEYWORD_RE.search(entry_text or combined_text):
            result.predicted_bucket = "D"
            result.bucket_reason = "投稿页正文命中收费关键词"
            result.predict_confidence = 0.75
            return result

        emails = set(m.group(0).lower() for m in EMAIL_RE.finditer(combined_text))
        if any(e.startswith(BIZ_EMAIL_PREFIXES) for e in emails):
            result.contact_email_type = "commercial"
            result.predicted_bucket = "D"
            result.bucket_reason = "联系邮箱为商务型前缀 (seo@/partnerships@/marketing@/sales@/bd@)"
            result.predict_confidence = 0.6
            return result
        elif emails:
            result.contact_email_type = "editorial"

        if domain.lower() in blacklist:
            result.marketplace_hit = "local_blacklist"
            result.predicted_bucket = "D"
            result.bucket_reason = "域名命中本地外链市场黑名单"
            result.predict_confidence = 0.9
            return result

        # --- queue signal (bias toward C) ---
        queue_signal = bool(QUEUE_KEYWORD_RE.search(combined_text) or PORTFOLIO_RE.search(entry_text))
        result.raw["queue_signal"] = queue_signal

        # --- activity signal ---
        result.latest_author_post = _detect_activity(session, base)
        tendency = _activity_tendency(result.latest_author_post)
        result.raw["activity_tendency"] = tendency

        # --- platform fingerprint ---
        for name, pat in PLATFORM_SIGNATURES:
            if pat.search(home_text):
                result.platform = name
                break

        # --- combine into predicted bucket ---
        if tendency == "stale":
            result.predicted_bucket = "stale"
            result.bucket_reason = "查不到 180 天内的外部署名文章，通道大概率已死"
            result.predict_confidence = 0.5 if result.latest_author_post is None else 0.65
        elif tendency == "aging":
            result.predicted_bucket = "C"
            result.bucket_reason = f"最新署名文章约 {result.latest_author_post}，落在 30-180 天内"
            result.predict_confidence = 0.55
        else:  # fresh
            if queue_signal:
                result.predicted_bucket = "B"
                result.bucket_reason = "近期有署名文章发布，但投稿页显示需排队审核"
                result.predict_confidence = 0.55
            elif result.platform in FORUM_PLATFORMS:
                result.predicted_bucket = "A"
                result.bucket_reason = f"论坛类平台 ({result.platform})，且 30 天内有活跃发布"
                result.predict_confidence = 0.7
            elif result.entry_url:
                result.predicted_bucket = "B"
                result.bucket_reason = "找到投稿入口且 30 天内有活跃发布，未见排队信号"
                result.predict_confidence = 0.55
            else:
                result.predicted_bucket = "unknown"
                result.bucket_reason = "30 天内有活跃发布，但未定位到投稿入口，需人工确认"
                result.predict_confidence = 0.3

        result.raw["paths_found"] = result.paths_found
        result.raw["emails"] = sorted(emails)
        return result
    finally:
        if own_session:
            session.close()


def probe_batch(domains: list[str], concurrency: int = 8, on_result=None, force: bool = False) -> list[ProbeResult]:
    """Probe many domains concurrently. `on_result(result)` is called from
    the calling thread (not the worker pool) as each domain finishes, so
    callers can stream progress and write to a single sqlite connection
    — which isn't thread-safe — without waiting for the whole batch."""
    blacklist = _load_marketplace_blacklist()
    results: list[ProbeResult] = []
    lock = threading.Lock()

    def _worker(d: str) -> ProbeResult:
        try:
            return probe_site(d, blacklist=blacklist, force=force)
        except Exception as exc:  # noqa: BLE001 - never let one domain kill the batch
            r = ProbeResult(domain=d)
            r.predicted_bucket = "unknown"
            r.bucket_reason = f"探测异常，需人工检查: {exc}"
            r.raw["error"] = str(exc)
            return r

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = {pool.submit(_worker, d): d for d in domains}
        for fut in concurrent.futures.as_completed(futures):
            res = fut.result()
            with lock:
                results.append(res)
            if on_result:
                on_result(res)
    return results


def result_to_row(result: ProbeResult) -> dict:
    raw = dict(result.raw)
    raw["bucket_reason"] = result.bucket_reason
    raw["entry_url"] = result.entry_url
    return {
        "paths_found": json.dumps(result.paths_found, ensure_ascii=False),
        "latest_author_post": result.latest_author_post,
        "has_pricing_page": int(result.has_pricing_page),
        "contact_email_type": result.contact_email_type,
        "marketplace_hit": result.marketplace_hit,
        "platform": result.platform,
        "predicted_bucket": result.predicted_bucket,
        "predict_confidence": result.predict_confidence,
        "raw": json.dumps(raw, ensure_ascii=False, default=str),
    }
