"""Post pattern analysis — what performs, by a configurable, clickbait-aware metric.

Samples a subreddit's posts and reports which features correlate with a chosen
performance metric (upvotes, comments, discussion quality, or clickbait-damped
"quality"). Also measures whether the sub actually rewards clickbait, so the
guidance doesn't push you toward it. Correlations from a sample, not the algorithm.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List

import praw
from prawcore import NotFound, Forbidden, TooManyRequests, ResponseException

from .helpers import (
    clean_subreddit_name, submission_to_features, features_from_arctic,
    safe_mean, winning_keywords, percentile, metric_value, engagement_ratio,
    trimmed_mean,
)
from .constants import STRONG_PERCENTILE, VIRAL_PERCENTILE
from . import arctic

# time_filter -> Arctic lookback window (label, days) for the archive source.
_ARCHIVE_WINDOW = {"day": "7d", "week": "21d", "month": "60d", "year": "365d", "all": "365d"}
_WINDOW_DAYS = {"day": 7, "week": 21, "month": 60, "year": 365, "all": 365}
_VALID_METRICS = {"score", "comments", "discussion", "quality"}


def _rows_from_archive(name: str, time_filter: str, limit: int) -> List[Dict[str, Any]]:
    """Pattern rows from the Arctic archive (no Reddit creds needed).

    Short windows use straight newest-first paging; longer windows (month+) use
    stratified sampling so the sample represents the whole period, not just the
    last few days of a high-volume sub.
    """
    if time_filter in ("month", "year", "all"):
        window_days = _WINDOW_DAYS.get(time_filter, 60)
        slices = 6 if window_days >= 300 else 4
        posts = arctic.fetch_stratified(name, window_days=window_days,
                                        slices=slices, per_slice=max(limit // slices, 40))
    else:
        posts = arctic.fetch_many_posts(name, after=_ARCHIVE_WINDOW.get(time_filter, "60d"),
                                        before="2d", target=max(limit, 100))
    rows = [features_from_arctic(p) for p in posts
            if not p.get("stickied") and p.get("removed_by_category") is None]
    return [r for r in rows if not r.get("recurring")]  # drop megathreads/AMAs


def _median(vals: List[float]) -> float:
    s = sorted(vals)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return round((s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2), 2)


def _group_stats(rows: List[Dict[str, Any]], key: str, perf: str,
                 min_n: int = 3, threshold: float = None) -> List[Dict[str, Any]]:
    """Group by a categorical feature; rank by median (outlier-robust), mean as
    tiebreak. Only buckets with >= min_n samples are eligible, so a single lucky
    post can't crown a category. When `threshold` is given, each bucket also
    reports its hit_rate: the share of posts at or above that threshold — a
    robust "how often does a strong post land here" signal.
    """
    buckets: Dict[Any, List[float]] = defaultdict(list)
    for r in rows:
        buckets[r.get(key)].append(r[perf])
    out = []
    for k, v in buckets.items():
        if len(v) < min_n:
            continue
        entry = {"value": k, "median": _median(v), "mean": safe_mean(v), "count": len(v)}
        if threshold is not None:
            entry["hit_rate"] = round(sum(1 for x in v if x >= threshold) / len(v), 2)
        out.append(entry)
    out.sort(key=lambda d: (d["median"], d["mean"]), reverse=True)
    return out


def _bool_lift(rows: List[Dict[str, Any]], key: str, perf: str,
               min_n: int = 5) -> Dict[str, Any]:
    """Median performance with vs without a boolean feature, plus a reliability
    flag (both groups need >= min_n samples for the lift to be trustworthy)."""
    on = [r[perf] for r in rows if r.get(key)]
    off = [r[perf] for r in rows if not r.get(key)]
    on_med, off_med = _median(on), _median(off)
    on_avg, off_avg = safe_mean(on), safe_mean(off)
    # Lift on means (median is often 0 in low-engagement subs).
    lift = round((on_avg / off_avg - 1) * 100, 1) if off_avg else 0.0
    return {"with_avg_score": on_avg, "without_avg_score": off_avg,
            "with_median": on_med, "without_median": off_med,
            "lift_pct": lift, "sample_with": len(on),
            "reliable": len(on) >= min_n and len(off) >= min_n}


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


def _share(rows: List[Dict[str, Any]], key: str) -> float:
    return round(sum(1 for r in rows if r.get(key)) / len(rows), 2) if rows else 0.0


def _dominant(rows: List[Dict[str, Any]], key: str):
    """Most common value of `key` among rows, with its share."""
    counts: Dict[Any, int] = defaultdict(int)
    for r in rows:
        counts[r.get(key)] += 1
    if not counts:
        return None, 0.0
    val, c = max(counts.items(), key=lambda kv: kv[1])
    return val, round(c / len(rows), 2)


def _viral_profile(rows: List[Dict[str, Any]], perf: str,
                   threshold: float) -> Dict[str, Any]:
    """Describe what the top-decile (viral) posts have in common, and which
    traits are over-represented versus the rest — the concrete 'viral recipe'.
    """
    viral = [r for r in rows if r[perf] >= threshold and r[perf] > 0]
    rest = [r for r in rows if r[perf] < threshold]
    if len(viral) < 5:
        return {"available": False, "reason": "too few viral posts to profile"}

    media, media_share = _dominant(viral, "media_type")
    flair, flair_share = _dominant(viral, "flair")
    block, block_share = _dominant(viral, "time_block")

    def over(key):
        v, r = _share(viral, key), _share(rest, key)
        return {"viral": v, "rest": r, "overrepresented": v > r + 0.05}

    def cb_share(rs):
        return round(sum(1 for r in rs if r.get("clickbait", 0) >= 0.4) / len(rs), 2) if rs else 0.0

    title = {
        "median_char_length": _median([r["char_length"] for r in viral]),
        "question": over("is_question"),
        "showcase": over("is_showcase"),
        "has_number": over("has_number"),
        "clickbait": {"viral": cb_share(viral), "rest": cb_share(rest),
                      "overrepresented": cb_share(viral) > cb_share(rest) + 0.05},
    }
    kws = [k["word"] for k in winning_keywords(viral, top_frac=0.6, min_count=2, score_key=perf)][:8]

    return {
        "available": True,
        "viral_threshold": threshold,
        "viral_count": len(viral),
        "recipe": {
            "media_type": {"value": media, "share": media_share},
            "flair": {"value": flair, "share": flair_share},
            "time_block_utc": {"value": block, "share": block_share},
            "title": title,
            "keywords": kws,
        },
    }


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
            rows = [r for r in rows if not r.get("recurring")]
            source_label = f"{listing_type}/{time_filter if listing_type == 'top' else ''}".rstrip("/")
        except NotFound:
            return {"error": f"Subreddit r/{name} not found", "status_code": 404}
        except Forbidden:
            return {"error": f"r/{name} is private or banned", "status_code": 403}
        except (TooManyRequests, ResponseException) as e:
            return {"error": f"Reddit API error: {e}"}

    if not rows:
        return {"error": "No posts sampled", "subreddit": name}

    # Precompute the chosen metric and derived buckets per row.
    for r in rows:
        r["_perf"] = metric_value(r, metric)
        r["length_band"] = ("short (<40)" if r["char_length"] < 40
                            else "medium (40-80)" if r["char_length"] <= 80 else "long (>80)")
        h = r["hour_utc"]
        r["time_block"] = ("00-06 UTC" if h < 6 else "06-12 UTC" if h < 12
                           else "12-18 UTC" if h < 18 else "18-24 UTC")
    rows.sort(key=lambda r: r["_perf"], reverse=True)

    perf = "_perf"
    vals = [r[perf] for r in rows]
    n = len(rows)

    # Actual time coverage: a high-volume sub may only span a few days even for
    # a 'month' request, which matters for interpreting the results.
    times = [r["created_utc"] for r in rows if r.get("created_utc")]
    span_days = round((max(times) - min(times)) / 86400.0, 1) if len(times) >= 2 else 0.0
    date_range = None
    if times:
        date_range = {
            "oldest": datetime.fromtimestamp(min(times), tz=timezone.utc).strftime("%Y-%m-%d"),
            "newest": datetime.fromtimestamp(max(times), tz=timezone.utc).strftime("%Y-%m-%d"),
        }

    # Confidence combines sample size and how well the window was covered.
    confidence = "high" if n >= 80 else "medium" if n >= 30 else "low"
    if confidence == "high" and span_days and span_days < 3:
        confidence = "medium"  # lots of posts but only a sliver of time

    # "Strong post" threshold = 75th percentile of the metric. Timing buckets
    # rank by hit_rate (share of strong posts), which is robust to outliers.
    strong = percentile(sorted(vals), STRONG_PERCENTILE)
    strong90 = percentile(sorted(vals), VIRAL_PERCENTILE)  # top-decile = "viral"

    def _by_hit(rows_, key, min_n):
        stats = _group_stats(rows_, key, perf, min_n=min_n, threshold=strong)
        stats.sort(key=lambda d: (d.get("hit_rate", 0), d["median"]), reverse=True)
        return stats

    best_hours = [{"hour_utc": b["value"], "hit_rate": b.get("hit_rate"), "median": b["median"],
                   "mean": b["mean"], "posts": b["count"]} for b in _by_hit(rows, "hour_utc", 3)][:5]
    time_blocks = [{"block": b["value"], "hit_rate": b.get("hit_rate"), "median": b["median"],
                    "mean": b["mean"], "posts": b["count"]} for b in _by_hit(rows, "time_block", 5)]
    best_days = [{"day": b["value"], "hit_rate": b.get("hit_rate"), "median": b["median"],
                  "mean": b["mean"], "posts": b["count"]} for b in _by_hit(rows, "weekday_name", 3)]

    disc_ratios = [engagement_ratio(r["score"], r["num_comments"]) for r in rows]

    return {
        "subreddit": name,
        "sampled": n,
        "confidence": confidence,
        "sample_span_days": span_days,
        "sample_date_range": date_range,
        "source": source_label,
        "metric": metric,
        "score_stats": {"mean": safe_mean(vals), "median": _median(vals),
                        "trimmed_mean": trimmed_mean(vals), "max": max(vals)},
        "score_percentiles": {q: percentile(sorted(vals), q) for q in (25, 50, 75, 90, 95)},
        "engagement": {
            "median_comments_per_upvote": _median(disc_ratios),
            "median_comments": _median([r["num_comments"] for r in rows]),
        },
        "clickbait_effect": _clickbait_effect(rows, perf),
        "viral_profile": _viral_profile(rows, perf, strong90),
        "best_time_blocks": time_blocks,
        "best_posting_hours_utc": best_hours,
        "best_posting_days": best_days,
        "score_by_media_type": _group_stats(rows, "media_type", perf, min_n=3),
        "score_by_flair": _group_stats(rows, "flair", perf, min_n=3)[:8],
        "title_length_bands": _group_stats(rows, "length_band", perf, min_n=3),
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
