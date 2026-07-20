"""Arctic Shift client — historical Reddit data (Pushshift successor).

Arctic Shift (https://github.com/ArthurHeitmann/arctic_shift) archives posts at
creation time and exposes them via a free, rate-limited API. We use it for two
things PRAW can't do well:

1. Removal detection (reveddit-style): Arctic keeps posts that were later
   mod-removed; diffing them against the live Reddit API reveals removals that
   PRAW's `.new()` listing silently hides.
2. Velocity/timing: server-side `created_utc` aggregation over a large,
   unbiased window for better traffic and best-time estimates.

Everything here fails soft — callers should fall back to PRAW-only analysis if
Arctic is unavailable. stdlib-only (urllib) to keep dependencies slim.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

ARCTIC_BASE = "https://arctic-shift.photon-reddit.com"
_UA = "reddit-analyzer/0.1 (archive diff)"

# Per-process response cache. Compare/patterns/draft often hit the same
# subreddit windows; caching avoids redundant calls and rate-limit hits.
_CACHE: Dict[str, Dict[str, Any]] = {}
_CACHE_ENABLED = True


def clear_cache() -> None:
    """Drop all cached Arctic responses (useful for tests or long sessions)."""
    _CACHE.clear()


class ArcticUnavailable(Exception):
    """Raised when the Arctic Shift service can't be reached or errored."""


def _get(path: str, params: Dict[str, Any], timeout: int = 20,
         retries: int = 2, backoff: float = 1.5) -> Dict[str, Any]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{ARCTIC_BASE}{path}?{query}"
    if _CACHE_ENABLED and url in _CACHE:
        return _CACHE[url]
    req = urllib.request.Request(url, headers={"User-Agent": _UA})

    last_err = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.load(resp)
            if _CACHE_ENABLED:
                _CACHE[url] = data
            return data
        except urllib.error.HTTPError as e:
            # Arctic returns 422/429 with {"error": "Timeout. Maybe slow down"}
            # when rate-limited — those are worth retrying with backoff.
            detail = ""
            try:
                detail = json.loads(e.read().decode()).get("error", "")
            except Exception:
                pass
            last_err = ArcticUnavailable(f"Arctic HTTP {e.code}: {detail}".strip())
            retryable = e.code in (422, 429, 500, 502, 503) or "timeout" in detail.lower()
            if not retryable or attempt == retries:
                raise last_err from e
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            last_err = ArcticUnavailable(f"Arctic request failed: {e}")
            if attempt == retries:
                raise last_err from e
        time.sleep(backoff * (attempt + 1))
    raise last_err  # pragma: no cover


def fetch_recent_posts(
    subreddit: str,
    after: str = "14d",
    before: Optional[str] = None,
    limit: int = 100,
    sort: str = "desc",
) -> List[Dict[str, Any]]:
    """Fetch archived posts for a subreddit within a time window.

    `after`/`before` accept Arctic offsets like '7d', '2d', '1month', or ISO
    dates. Use `before='2d'` for score-based analysis: posts younger than
    ~36h have unsettled (0/1) scores in the archive.
    Returns the raw archived post dicts.
    """
    data = _get("/api/posts/search", {
        "subreddit": subreddit,
        "after": after,
        "before": before,
        "limit": max(1, min(limit, 100)),
        "sort": sort,
    })
    payload = data.get("data", data)
    return payload if isinstance(payload, list) else []


def fetch_many_posts(
    subreddit: str,
    after: str = "180d",
    before: str = "2d",
    target: int = 300,
    page: int = 100,
    delay: float = 1.0,
) -> List[Dict[str, Any]]:
    """Page backwards through the archive to collect up to `target` posts.

    Arctic caps each request at 100, so this walks the `before` cursor back in
    time. A small `delay` between pages keeps us under the free rate limit.
    Returns whatever it gathered; partial results on rate-limit are fine.
    """
    out: List[Dict[str, Any]] = []
    seen: set = set()
    cursor = before
    while len(out) < target:
        try:
            batch = fetch_recent_posts(subreddit, after=after, before=cursor,
                                       limit=page, sort="desc")
        except ArcticUnavailable:
            break  # keep what we have
        if not batch:
            break
        fresh = [p for p in batch if p.get("id") and p["id"] not in seen]
        if not fresh:
            break
        for p in fresh:
            seen.add(p["id"])
        out.extend(fresh)
        oldest = min((p.get("created_utc", 0) or 0) for p in batch)
        if not oldest or len(batch) < page:
            break
        cursor = int(oldest)  # epoch seconds; next page is strictly older
        if len(out) < target:
            time.sleep(delay)
    return out[:target]


def aggregate_post_frequency(
    subreddit: str,
    after: str = "90d",
    frequency: str = "hour",
) -> List[Dict[str, Any]]:
    """Server-side post-count aggregation by created_utc.

    frequency: 'hour' | 'day' | 'week' | 'month'. Returns
    [{'created_utc': <iso>, 'count': <str>}, ...]. Note: the aggregate endpoint
    rejects a `limit` param and requires an offset `after` (e.g. '30d') or an
    explicit `after`+`before` range.
    """
    data = _get("/api/posts/search/aggregate", {
        "subreddit": subreddit,
        "after": after,
        "aggregate": "created_utc",
        "frequency": frequency,
    })
    payload = data.get("data", data)
    return payload if isinstance(payload, list) else []
