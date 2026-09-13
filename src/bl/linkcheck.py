"""Link survival checking: is a published backlink still on the page,
and is it still dofollow?
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import requests

from .prober import USER_AGENT, TIMEOUT, RETRIES

REL_NOFOLLOW_RE = re.compile(r"nofollow|ugc|sponsored", re.IGNORECASE)


@dataclass
class LinkCheckResult:
    http_status: Optional[int]
    link_present: bool
    rel_attr: Optional[str]


def _fetch(url: str) -> Optional[requests.Response]:
    for attempt in range(RETRIES + 1):
        try:
            return requests.get(url, timeout=TIMEOUT, headers={"User-Agent": USER_AGENT}, allow_redirects=True)
        except requests.RequestException:
            if attempt == RETRIES:
                return None
    return None


def check_link(live_url: str, target_domain: str) -> LinkCheckResult:
    resp = _fetch(live_url)
    if resp is None:
        return LinkCheckResult(http_status=None, link_present=False, rel_attr=None)
    if resp.status_code != 200:
        return LinkCheckResult(http_status=resp.status_code, link_present=False, rel_attr=None)

    target = re.escape(target_domain)
    # find an <a ...href="...target_domain...">...</a> tag and pull its rel attribute
    anchor_re = re.compile(
        r"<a\b([^>]*\bhref=[\"'][^\"']*" + target + r"[^\"']*[\"'][^>]*)>",
        re.IGNORECASE,
    )
    m = anchor_re.search(resp.text)
    if not m:
        return LinkCheckResult(http_status=resp.status_code, link_present=False, rel_attr=None)

    attrs = m.group(1)
    rel_m = re.search(r'rel=["\']([^"\']+)["\']', attrs, re.IGNORECASE)
    if not rel_m:
        rel_attr = "dofollow"
    elif REL_NOFOLLOW_RE.search(rel_m.group(1)):
        rel_attr = rel_m.group(1).lower()
    else:
        rel_attr = "dofollow"
    return LinkCheckResult(http_status=resp.status_code, link_present=True, rel_attr=rel_attr)
