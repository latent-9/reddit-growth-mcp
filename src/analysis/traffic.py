"""Subreddit traffic estimation and target discovery.

Reddit's public API does NOT expose true daily unique visitors (that lives
behind moderator-only traffic stats). We therefore estimate reach from public
signals: subscriber count, currently-active users, and post/comment velocity.
Every number returned here is clearly labelled as an estimate.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

import praw
from prawcore import Forbidden, NotFound, ResponseException, TooManyRequests

from . import arctic
from .helpers import clean_subreddit_name, features_from_arctic, median, safe_mean


def _velocity_tier(posts_per_day: float) -> str:
    if posts_per_day >= 200:
        return "very_high"
    if posts_per_day >= 50:
        return "high"
    if posts_per_day >= 10:
        return "medium"
    if posts_per_day >= 1:
        return "low"
    return "minimal"


def estimate_activity_archive(
    subreddit_name: str,
    window: str = "30d",
    sample: int = 200,
    ctx: Any = None,
) -> Dict[str, Any]:
    """Estimate a subreddit's activity from the Arctic archive — no creds needed.

    Reddit hides subscriber/visitor counts from the public API, and Arctic has no
    subscriber data, so we report posting/comment velocity as the traffic proxy.
    """
    name = clean_subreddit_name(subreddit_name)
    try:
        posts = arctic.fetch_many_posts(name, after=window, before="2d", target=sample)
    except arctic.ArcticUnavailable as e:
        return {"error": f"Archive unavailable: {e}", "subreddit": name}
    if not posts:
        return {"error": "No archived posts found", "subreddit": name}

    times = sorted(p.get("created_utc", 0) or 0 for p in posts)
    span_days = (times[-1] - times[0]) / 86400.0 if len(times) >= 2 else 0.0
    posts_per_day = round(len(posts) / span_days, 1) if span_days > 0 else 0.0

    rows = [features_from_arctic(p) for p in posts]
    live = [r for r in rows if r["removal_status"] == "live"]
    med_comments = median([r["num_comments"] for r in live])
    med_score = median([r["score"] for r in live])

    return {
        "subreddit": name,
        "source": "archive",
        "signals": {
            "posts_per_day_est": posts_per_day,
            "median_comments_per_post": int(med_comments) if med_comments == int(med_comments) else med_comments,
            "median_score": int(med_score) if med_score == int(med_score) else med_score,
            "sample": len(posts),
            "span_days": round(span_days, 1),
        },
        "activity_tier": _velocity_tier(posts_per_day),
        "disclaimer": (
            "Velocity-based estimate from public archive data. Reddit "
            "does not expose subscriber or visitor counts publicly."
        ),
    }


def _activity_tier(estimated_daily_visitors: float) -> str:
    if estimated_daily_visitors >= 200_000:
        return "very_high"
    if estimated_daily_visitors >= 50_000:
        return "high"
    if estimated_daily_visitors >= 10_000:
        return "medium"
    if estimated_daily_visitors >= 1_000:
        return "low"
    return "minimal"


def estimate_subreddit_traffic(
    subreddit_name: str,
    reddit: praw.Reddit,
    sample_size: int = 50,
    ctx: Any = None,
) -> Dict[str, Any]:
    """Estimate a subreddit's reach from public signals.

    Combines subscriber count, active users, and the posting velocity of the
    most recent `sample_size` posts into a rough daily-visitor estimate.
    """
    name = clean_subreddit_name(subreddit_name)
    try:
        sub = reddit.subreddit(name)
        subscribers = int(sub.subscribers or 0)
        active = int(getattr(sub, "accounts_active", None) or getattr(sub, "active_user_count", 0) or 0)
    except NotFound:
        return {"error": f"Subreddit r/{name} not found", "status_code": 404}
    except Forbidden:
        return {"error": f"r/{name} is private or banned", "status_code": 403}
    except TooManyRequests as e:
        return {
            "error": "Rate limited by Reddit",
            "status_code": 429,
            "retry_after_seconds": getattr(e, "retry_after", None),
        }
    except ResponseException as e:
        return {
            "error": f"Reddit API error: {e}",
            "status_code": getattr(getattr(e, "response", None), "status_code", None),
        }

    # Posting velocity from the newest posts.
    posts_per_day = 0.0
    comments_per_post = 0.0
    avg_score = 0.0
    try:
        recent = list(sub.new(limit=sample_size))
        if len(recent) >= 2:
            newest = recent[0].created_utc
            oldest = recent[-1].created_utc
            span_days = max((newest - oldest) / 86400.0, 1e-6)
            posts_per_day = round(len(recent) / span_days, 1)
            comments_per_post = safe_mean([p.num_comments for p in recent])
            avg_score = safe_mean([p.score for p in recent])
    except (TooManyRequests, ResponseException):
        pass  # keep the subscriber/active signals we already have

    # Heuristic daily-visitor estimate (explicitly rough):
    #   - active users on the page at any moment scale up to daily uniques
    #   - subscribers contribute a small daily return-visit fraction
    #   - engagement (comments/day) is a lurker-to-visitor multiplier
    comments_per_day = posts_per_day * comments_per_post
    estimated_daily_visitors = int(active * 12 + subscribers * 0.02 + comments_per_day * 5)

    return {
        "subreddit": name,
        "signals": {
            "subscribers": subscribers,
            "active_users_now": active,
            "posts_per_day_est": posts_per_day,
            "avg_comments_per_post": comments_per_post,
            "avg_score_recent": avg_score,
        },
        "estimated_daily_visitors": estimated_daily_visitors,
        "activity_tier": _activity_tier(estimated_daily_visitors),
        "meets_50k_threshold": estimated_daily_visitors >= 50_000,
        "disclaimer": "Estimate only. Reddit does not expose true daily visitors publicly.",
    }


def find_target_subreddits(
    topics: Union[str, List[str]],
    reddit: praw.Reddit,
    limit_per_topic: int = 15,
    min_subscribers: int = 10_000,
    min_daily_visitors: int = 50_000,
    include_nsfw: bool = False,
    ctx: Any = None,
) -> Dict[str, Any]:
    """Discover and rank subreddits for the given topics by estimated reach.

    Uses Reddit's own subreddit search (no external index), then scores each
    unique community with `estimate_subreddit_traffic`.
    """
    if isinstance(topics, str):
        topics = [topics]

    seen: Dict[str, Any] = {}
    for topic in topics:
        try:
            for sub in reddit.subreddits.search(topic, limit=limit_per_topic):
                key = sub.display_name.lower()
                if key in seen:
                    seen[key]["matched_topics"].append(topic)
                    continue
                if getattr(sub, "over18", False) and not include_nsfw:
                    continue
                seen[key] = {"subreddit_obj": sub, "matched_topics": [topic]}
        except TooManyRequests:
            return {"error": "Rate limited by Reddit during search", "status_code": 429, "partial_results": len(seen)}
        except ResponseException:
            continue  # skip a failing topic, keep going

    results: List[Dict[str, Any]] = []
    total = len(seen)
    for key, entry in seen.items():
        est = estimate_subreddit_traffic(key, reddit, sample_size=25)
        if "error" in est:
            continue
        if est["signals"]["subscribers"] < min_subscribers:
            continue
        results.append(
            {
                "subreddit": est["subreddit"],
                "matched_topics": entry["matched_topics"],
                "subscribers": est["signals"]["subscribers"],
                "active_users_now": est["signals"]["active_users_now"],
                "posts_per_day_est": est["signals"]["posts_per_day_est"],
                "avg_score_recent": est["signals"]["avg_score_recent"],
                "estimated_daily_visitors": est["estimated_daily_visitors"],
                "activity_tier": est["activity_tier"],
                "meets_threshold": est["estimated_daily_visitors"] >= min_daily_visitors,
            }
        )

    results.sort(key=lambda r: r["estimated_daily_visitors"], reverse=True)
    qualifying = [r for r in results if r["meets_threshold"]]

    return {
        "topics": topics,
        "total_discovered": total,
        "returned": len(results),
        "qualifying_count": len(qualifying),
        "min_daily_visitors": min_daily_visitors,
        "subreddits": results,
        "disclaimer": "Daily-visitor figures are estimates from public signals.",
    }
