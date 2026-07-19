"""Viral / high-engagement post pattern analysis.

Samples a subreddit's top posts and reports which features correlate with high
scores: title style, media type, flair, and best posting windows. Reddit's
ranking is not public, so these are empirical correlations, not the algorithm.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

import praw
from prawcore import NotFound, Forbidden, TooManyRequests, ResponseException

from .helpers import (
    clean_subreddit_name, submission_to_features, features_from_arctic,
    safe_mean, winning_keywords,
)
from . import arctic

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# time_filter -> Arctic lookback window for the archive source.
_ARCHIVE_WINDOW = {"day": "7d", "week": "21d", "month": "60d", "year": "365d", "all": "365d"}


def _rows_from_archive(name: str, time_filter: str, limit: int) -> List[Dict[str, Any]]:
    """Pattern rows from the Arctic archive (no Reddit creds needed).

    Pages back through the window (excluding the last ~2 days so scores are
    settled), then sorts by score to mirror a 'top' listing.
    """
    window = _ARCHIVE_WINDOW.get(time_filter, "60d")
    posts = arctic.fetch_many_posts(name, after=window, before="2d",
                                    target=max(limit, 100))
    rows = [features_from_arctic(p) for p in posts
            if not p.get("stickied") and p.get("removed_by_category") is None]
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def _avg_score_by(rows: List[Dict[str, Any]], key: str) -> List[Dict[str, Any]]:
    """Average score grouped by a categorical feature, ranked high to low."""
    buckets: Dict[Any, List[int]] = defaultdict(list)
    for r in rows:
        buckets[r.get(key)].append(r["score"])
    ranked = sorted(
        ({"value": k, "avg_score": safe_mean(v), "count": len(v)} for k, v in buckets.items()),
        key=lambda d: d["avg_score"], reverse=True,
    )
    return ranked


def _bool_lift(rows: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    """Compare average score when a boolean feature is on vs off."""
    on = [r["score"] for r in rows if r.get(key)]
    off = [r["score"] for r in rows if not r.get(key)]
    on_avg, off_avg = safe_mean(on), safe_mean(off)
    lift = round((on_avg / off_avg - 1) * 100, 1) if off_avg else 0.0
    return {"with_avg_score": on_avg, "without_avg_score": off_avg,
            "lift_pct": lift, "sample_with": len(on)}


def analyze_post_patterns(
    subreddit_name: str,
    reddit: praw.Reddit = None,
    listing_type: str = "top",
    time_filter: str = "month",
    limit: int = 100,
    source: str = "auto",
    ctx: Any = None,
) -> Dict[str, Any]:
    """Find what makes top posts perform in a given subreddit.

    source: 'auto' uses Reddit when available, else the Arctic archive;
    'reddit' forces PRAW; 'archive' forces Arctic (no creds needed).
    """
    name = clean_subreddit_name(subreddit_name)
    use_archive = source == "archive" or (source == "auto" and reddit is None)

    if use_archive:
        try:
            rows = _rows_from_archive(name, time_filter, limit)
            source_label = f"archive/{_ARCHIVE_WINDOW.get(time_filter, '60d')}"
        except arctic.ArcticUnavailable as e:
            return {"error": f"Archive unavailable: {e}", "subreddit": name,
                    "hint": "Add Reddit credentials to use the live source."}
    else:
        try:
            sub = reddit.subreddit(name)
            if listing_type == "top":
                listing = sub.top(time_filter=time_filter, limit=limit)
            elif listing_type == "hot":
                listing = sub.hot(limit=limit)
            else:
                listing = sub.new(limit=limit)
            rows = [submission_to_features(p) for p in listing if not p.stickied]
            source_label = f"{listing_type}/{time_filter if listing_type == 'top' else ''}".rstrip("/")
        except NotFound:
            return {"error": f"Subreddit r/{name} not found", "status_code": 404}
        except Forbidden:
            return {"error": f"r/{name} is private or banned", "status_code": 403}
        except (TooManyRequests, ResponseException) as e:
            return {"error": f"Reddit API error: {e}"}

    if not rows:
        return {"error": "No posts sampled", "subreddit": name}

    scores = [r["score"] for r in rows]
    hour_counts = {r["hour_utc"]: 0 for r in rows}
    hour_scores: Dict[int, List[int]] = defaultdict(list)
    weekday_scores: Dict[str, List[int]] = defaultdict(list)
    for r in rows:
        hour_scores[r["hour_utc"]].append(r["score"])
        weekday_scores[r["weekday_name"]].append(r["score"])

    best_hours = sorted(
        ({"hour_utc": h, "avg_score": safe_mean(s), "posts": len(s)} for h, s in hour_scores.items()),
        key=lambda d: d["avg_score"], reverse=True,
    )[:5]
    best_days = sorted(
        ({"day": d, "avg_score": safe_mean(s), "posts": len(s)} for d, s in weekday_scores.items()),
        key=lambda x: x["avg_score"], reverse=True,
    )

    # Winning title-length band.
    length_bands: Dict[str, List[int]] = defaultdict(list)
    for r in rows:
        band = ("short (<40)" if r["char_length"] < 40
                else "medium (40-80)" if r["char_length"] <= 80
                else "long (>80)")
        length_bands[band].append(r["score"])

    return {
        "subreddit": name,
        "sampled": len(rows),
        "source": source_label,
        "score_stats": {"avg": safe_mean(scores), "max": max(scores), "median": sorted(scores)[len(scores)//2]},
        "best_posting_hours_utc": best_hours,
        "best_posting_days": best_days,
        "score_by_media_type": _avg_score_by(rows, "media_type"),
        "score_by_flair": _avg_score_by(rows, "flair")[:8],
        "title_length_bands": [{"band": b, "avg_score": safe_mean(s), "posts": len(s)}
                               for b, s in length_bands.items()],
        "title_signal_lift": {
            "question_titles": _bool_lift(rows, "is_question"),
            "list_titles": _bool_lift(rows, "is_list"),
            "showcase_titles": _bool_lift(rows, "is_showcase"),
            "has_number": _bool_lift(rows, "has_number"),
            "has_emoji": _bool_lift(rows, "has_emoji"),
        },
        "winning_keywords": winning_keywords(rows),
        "top_examples": [
            {"title": r["title"], "score": r["score"], "flair": r["flair"],
             "media_type": r["media_type"], "permalink": r["permalink"]}
            for r in sorted(rows, key=lambda r: r["score"], reverse=True)[:5]
        ],
        "disclaimer": "Empirical correlations from a sample, not Reddit's ranking algorithm.",
    }
