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


class ArcticUnavailable(Exception):
    """Raised when the Arctic Shift service can't be reached or errored."""


def _get(path: str, params: Dict[str, Any], timeout: int = 20) -> Dict[str, Any]:
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    url = f"{ARCTIC_BASE}{path}?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        # Arctic returns 422 with {"error": "Timeout. Maybe slow down a bit"}
        # when rate-limited; surface that message so callers can back off.
        detail = ""
        try:
            detail = json.loads(e.read().decode()).get("error", "")
        except Exception:
            pass
        raise ArcticUnavailable(f"Arctic HTTP {e.code}: {detail}".strip()) from e
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
        raise ArcticUnavailable(f"Arctic request failed: {e}") from e


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
