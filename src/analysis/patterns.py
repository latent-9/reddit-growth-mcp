"""Post pattern analysis — what performs, by a configurable, clickbait-aware metric.

Samples a subreddit's posts and reports which features correlate with a chosen
performance metric (upvotes, comments, discussion quality, or clickbait-damped
"quality"). Also measures whether the sub actually rewards clickbait, so the
guidance doesn't push you toward it. Correlations from a sample, not the algorithm.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Dict, List

import praw
from prawcore import NotFound, Forbidden, TooManyRequests, ResponseException

from .helpers import (
    clean_subreddit_name, submission_to_features, features_from_arctic,
    safe_mean, winning_keywords, percentile, metric_value, engagement_ratio,
)
from . import arctic

# time_filter -> Arctic lookback window for the archive source.
_ARCHIVE_WINDOW = {"day": "7d", "week": "21d", "month": "60d", "year": "365d", "all": "365d"}
_VALID_METRICS = {"score", "comments", "discussion", "quality"}


def _rows_from_archive(name: str, time_filter: str, limit: int) -> List[Dict[str, Any]]:
    """Pattern rows from the Arctic archive (no Reddit creds needed)."""
    window = _ARCHIVE_WINDOW.get(time_filter, "60d")
    posts = arctic.fetch_many_posts(name, after=window, before="2d", target=max(limit, 100))
    return [features_from_arctic(p) for p in posts
            if not p.get("stickied") and p.get("removed_by_category") is None]


def _avg_by(rows: List[Dict[str, Any]], key: str, perf: str) -> List[Dict[str, Any]]:
    """Average performance grouped by a categorical feature, ranked high to low."""
    buckets: Dict[Any, List[float]] = defaultdict(list)
    for r in rows:
        buckets[r.get(key)].append(r[perf])
    return sorted(
        ({"value": k, "avg_score": safe_mean(v), "count": len(v)} for k, v in buckets.items()),
        key=lambda d: d["avg_score"], reverse=True,
    )


def _bool_lift(rows: List[Dict[str, Any]], key: str, perf: str) -> Dict[str, Any]:
    """Compare average performance when a boolean feature is on vs off."""
    on = [r[perf] for r in rows if r.get(key)]
    off = [r[perf] for r in rows if not r.get(key)]
    on_avg, off_avg = safe_mean(on), safe_mean(off)
    lift = round((on_avg / off_avg - 1) * 100, 1) if off_avg else 0.0
    return {"with_avg_score": on_avg, "without_avg_score": off_avg,
            "lift_pct": lift, "sample_with": len(on)}


def _clickbait_effect(rows: List[Dict[str, Any]], perf: str) -> Dict[str, Any]:
    """Does clickbait actually help in this sub? Reports the honest answer."""
    baity = [r[perf] for r in rows if r.get("clickbait", 0) >= 0.4]
    clean = [r[perf] for r in rows if r.get("clickbait", 0) < 0.4]
    baity_avg, clean_avg = safe_mean(baity), safe_mean(clean)
    lift = round((baity_avg / clean_avg - 1) * 100, 1) if clean_avg else 0.0
    if len(baity) < 3:
        verdict = "too_few_clickbait_samples"
    elif lift <= -10:
        verdict = "clickbait_penalized"
    elif lift >= 20:
        verdict = "clickbait_rewarded"
    else:
        verdict = "clickbait_neutral"
    return {"clickbait_avg": baity_avg, "clean_avg": clean_avg,
            "lift_pct": lift, "clickbait_sample": len(baity), "verdict": verdict}


def analyze_post_patterns(
    subreddit_name: str,
    reddit: praw.Reddit = None,
    listing_type: str = "top",
    time_filter: str = "month",
    limit: int = 100,
    source: str = "auto",
    metric: str = "score",
    ctx: Any = None,
) -> Dict[str, Any]:
    """Find what makes posts perform in a subreddit.

    metric: 'score' (upvotes) | 'comments' | 'discussion' (comments/upvote,
    anti-clickbait) | 'quality' (upvotes damped by a clickbait penalty).
    source: 'auto' | 'reddit' | 'archive' (archive needs no creds).
    """
    if metric not in _VALID_METRICS:
        metric = "score"
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
            listing = (sub.top(time_filter=time_filter, limit=limit) if listing_type == "top"
                       else sub.hot(limit=limit) if listing_type == "hot"
                       else sub.new(limit=limit))
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

    # Precompute the chosen performance metric per row.
    for r in rows:
        r["_perf"] = metric_value(r, metric)
    rows.sort(key=lambda r: r["_perf"], reverse=True)

    perf = "_perf"
    vals = [r[perf] for r in rows]
    hour_scores: Dict[int, List[float]] = defaultdict(list)
    weekday_scores: Dict[str, List[float]] = defaultdict(list)
    length_bands: Dict[str, List[float]] = defaultdict(list)
    for r in rows:
        hour_scores[r["hour_utc"]].append(r[perf])
        weekday_scores[r["weekday_name"]].append(r[perf])
        band = ("short (<40)" if r["char_length"] < 40
                else "medium (40-80)" if r["char_length"] <= 80 else "long (>80)")
        length_bands[band].append(r[perf])

    best_hours = sorted(
        ({"hour_utc": h, "avg_score": safe_mean(s), "posts": len(s)} for h, s in hour_scores.items()),
        key=lambda d: d["avg_score"], reverse=True)[:5]
    best_days = sorted(
        ({"day": d, "avg_score": safe_mean(s), "posts": len(s)} for d, s in weekday_scores.items()),
        key=lambda x: x["avg_score"], reverse=True)

    # Genuine-engagement snapshot (independent of the chosen metric).
    disc_ratios = [engagement_ratio(r["score"], r["num_comments"]) for r in rows]

    return {
        "subreddit": name,
        "sampled": len(rows),
        "source": source_label,
        "metric": metric,
        "score_stats": {"avg": safe_mean(vals), "max": max(vals),
                        "median": sorted(vals)[len(vals) // 2]},
        "score_percentiles": {q: percentile(sorted(vals), q) for q in (25, 50, 75, 90, 95)},
        "engagement": {
            "median_comments_per_upvote": sorted(disc_ratios)[len(disc_ratios) // 2],
            "avg_comments": safe_mean([r["num_comments"] for r in rows]),
        },
        "clickbait_effect": _clickbait_effect(rows, perf),
        "best_posting_hours_utc": best_hours,
        "best_posting_days": best_days,
        "score_by_media_type": _avg_by(rows, "media_type", perf),
        "score_by_flair": _avg_by(rows, "flair", perf)[:8],
        "title_length_bands": [{"band": b, "avg_score": safe_mean(s), "posts": len(s)}
                               for b, s in length_bands.items()],
        "title_signal_lift": {
            "question_titles": _bool_lift(rows, "is_question", perf),
            "list_titles": _bool_lift(rows, "is_list", perf),
            "showcase_titles": _bool_lift(rows, "is_showcase", perf),
            "has_number": _bool_lift(rows, "has_number", perf),
            "has_emoji": _bool_lift(rows, "has_emoji", perf),
        },
        "winning_keywords": winning_keywords(rows, score_key=perf),
        "top_examples": [
            {"title": r["title"], "score": r["score"], "num_comments": r["num_comments"],
             "clickbait": r["clickbait"], "flair": r["flair"],
             "media_type": r["media_type"], "permalink": r["permalink"]}
            for r in rows[:5]
        ],
        "disclaimer": "Empirical correlations from a sample, not Reddit's ranking algorithm.",
    }
