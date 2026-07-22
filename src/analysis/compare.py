"""Compare subreddits to decide where a post is most likely to land well.

Creds-free: everything is computed from the Arctic archive. For each subreddit
we combine how *forgiving* it is (low mod-removal rate) with how much *reach* a
typical surviving post gets (median score) into one opportunity score.
"""

from __future__ import annotations

from typing import Any, Dict, List, Union

from . import arctic
from .constants import (
    LOW_CONFIDENCE_FILTERED_RATIO,
    SAFETY_MODERATE_MAX,
    SAFETY_SAFE_MAX,
    VIRAL_PERCENTILE,
)
from .helpers import clean_subreddit_name, features_from_arctic, median, percentile, safe_mean


def _profile_subreddit(name: str, window: str, sample: int) -> Dict[str, Any]:
    posts = arctic.fetch_many_posts(name, after=window, before="2d", target=sample)
    if not posts:
        return {"subreddit": name, "error": "no archived posts (or rate-limited)"}

    # Posting velocity as a traffic proxy (Arctic gives no subscriber counts).
    times = sorted(p.get("created_utc", 0) or 0 for p in posts)
    span_days = (times[-1] - times[0]) / 86400.0 if len(times) >= 2 else 0.0
    posts_per_day = round(len(posts) / span_days, 1) if span_days > 0 else 0.0

    rows = [f for f in (features_from_arctic(p) for p in posts) if not f.get("recurring")]
    live = [r for r in rows if r["removal_status"] == "live"]
    removed = [r for r in rows if r["removal_status"] == "mod_removed"]
    filtered = [r for r in rows if r["removal_status"] == "filtered"]
    considered = len(live) + len(removed)
    removal_rate = round(len(removed) / considered, 3) if considered else 0.0
    # AutoMod-filtered posts are uncertain; a high share means low confidence.
    filtered_ratio = round(len(filtered) / len(rows), 2) if rows else 0.0
    low_confidence = filtered_ratio > LOW_CONFIDENCE_FILTERED_RATIO or considered < 10

    live_scores = [r["score"] for r in live]
    median_score = median(live_scores)
    _mc = median([r["num_comments"] for r in live])
    median_comments = int(_mc) if _mc == int(_mc) else _mc  # keep whole counts integer-looking
    # Opportunity: reach of a typical surviving post, discounted by removal risk.
    opportunity = round(median_score * (1 - removal_rate), 1)
    # Viral potential: the upside (90th-percentile reach) a strong post can hit
    # here, discounted by removal risk. This is what matters for going viral.
    ceiling = percentile(sorted(live_scores), VIRAL_PERCENTILE) if live_scores else 0
    viral_potential = round(ceiling * (1 - removal_rate), 1)
    # Growth score: reliable typical reach (steady karma) plus a fraction of the
    # viral upside. Both already discount removal risk, so safe + active subs win.
    growth_score = round(opportunity + 0.3 * viral_potential, 1)

    media = {}
    for r in live:
        media[r["media_type"]] = media.get(r["media_type"], 0) + 1
    top_media = max(media, key=media.get) if media else None

    # Safety = how likely a rule-abiding post survives (mean-mod risk).
    safety = (
        "safe" if removal_rate < SAFETY_SAFE_MAX else "moderate" if removal_rate < SAFETY_MODERATE_MAX else "strict"
    )

    return {
        "subreddit": name,
        "sampled": len(rows),
        "posts_per_day": posts_per_day,
        "removal_rate": removal_rate,
        "safety": safety,
        "median_score": median_score,
        "median_comments": median_comments,
        "viral_ceiling": ceiling,
        "viral_potential": viral_potential,
        "growth_score": growth_score,
        "avg_score": safe_mean(live_scores),
        "best_media": top_media,
        "opportunity_score": opportunity,
        "low_confidence": low_confidence,
        "automod_filtered_ratio": filtered_ratio,
    }


def compare_subreddits(
    subreddits: Union[str, List[str]],
    window: str = "60d",
    sample: int = 200,
    rank_by: str = "growth",
    ctx: Any = None,
) -> Dict[str, Any]:
    """Profile and rank subreddits (no creds needed).

    rank_by: 'growth' (default) balances reliable reach and viral upside for
    account growth; 'viral' ranks by viral upside alone; 'opportunity' ranks by
    the reach of a typical post.
    """
    if isinstance(subreddits, str):
        subreddits = [subreddits]
    names = [clean_subreddit_name(s) for s in subreddits if s and s.strip()]
    # De-dupe case-insensitively (r/MCP and r/mcp are the same sub), keep order.
    _seen: set[str] = set()
    names = [n for n in names if not (n.lower() in _seen or _seen.add(n.lower()))]
    if not names:
        return {"error": "Provide at least one subreddit name"}

    sort_key = {
        "viral": "viral_potential",
        "opportunity": "opportunity_score",
        "growth": "growth_score",
        "insight": "median_comments",
    }.get(rank_by, "growth_score")
    profiles = [_profile_subreddit(n, window, sample) for n in names]
    ranked = [p for p in profiles if "error" not in p]
    ranked.sort(key=lambda p: p[sort_key], reverse=True)
    failed = [p for p in profiles if "error" in p]

    criteria = {
        "growth": "growth = typical reach + 0.3 × viral potential (both removal-adjusted)",
        "viral": "viral potential = 90th-percentile reach × (1 − removal rate)",
        "opportunity": "opportunity = median reach × (1 − removal rate)",
        "insight": "insight = median comments per post (discussion depth)",
    }.get(rank_by, "growth")
    return {
        "ranked": ranked,
        "failed": failed,
        "ranked_by": rank_by,
        "best_pick": ranked[0]["subreddit"] if ranked else None,
        "criteria": criteria,
        "disclaimer": "Creds-free estimate from the Arctic archive; a sample, not a census.",
    }
