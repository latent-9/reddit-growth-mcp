"""Growth planner — turn a list of candidate subreddits into an action plan.

Ranks the subreddits for account growth, picks the safest strong one (avoiding
mod-heavy communities), reads its viral recipe, and returns a structured plan:
where to post, what to post, and when. Credential-free (uses the archive).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .compare import compare_subreddits
from .insight import analyze_insight
from .patterns import analyze_post_patterns


def build_growth_plan(
    subreddits: Union[str, List[str]],
    reddit: Any = None,
    window: str = "30d",
    sample: int = 90,
    time_filter: str = "month",
    ctx: Any = None,
) -> Dict[str, Any]:
    """Rank candidate subreddits and return an actionable growth plan."""
    comp = compare_subreddits(subreddits, window, sample, "growth")
    if "error" in comp or not comp.get("ranked"):
        return {"error": comp.get("error", "no data for the given subreddits")}

    ranked = comp["ranked"]
    eligible = [p for p in ranked if p.get("safety") != "strict" and not p.get("low_confidence")]
    target = (eligible or ranked)[0]
    also = [p for p in eligible if p["subreddit"] != target["subreddit"]][:4]
    avoided = [p["subreddit"] for p in ranked if p.get("safety") == "strict" or p.get("low_confidence")]

    recipe: Optional[Dict[str, Any]] = None
    best_hours: List[Dict[str, Any]] = []
    best_days: List[Dict[str, Any]] = []
    pat = analyze_post_patterns(target["subreddit"], reddit, "top", time_filter, 200, "auto")
    if "error" not in pat:
        vp = pat.get("viral_profile", {})
        if vp.get("available"):
            recipe = vp["recipe"]
        best_hours = pat.get("best_posting_hours_utc", [])[:3]
        best_days = pat.get("best_posting_days", [])[:2]

    # Discussion depth of the chosen target (one extra comment sample).
    ins = analyze_insight(target["subreddit"])
    insight_tier = ins.get("insight_tier") if "error" not in ins else None
    substantive_ratio = ins.get("substantive_ratio") if "error" not in ins else None

    return {
        "target": {
            "subreddit": target["subreddit"],
            "growth_score": target.get("growth_score"),
            "viral_potential": target.get("viral_potential"),
            "posts_per_day": target.get("posts_per_day"),
            "median_comments": target.get("median_comments"),
            "insight_tier": insight_tier,
            "substantive_ratio": substantive_ratio,
            "removal_rate": target.get("removal_rate"),
            "safety": target.get("safety"),
        },
        "also_consider": [
            {
                "subreddit": p["subreddit"],
                "growth_score": p.get("growth_score"),
                "removal_rate": p.get("removal_rate"),
                "safety": p.get("safety"),
            }
            for p in also
        ],
        "avoided": avoided,
        "recipe": recipe,
        "best_posting_hours_utc": best_hours,
        "best_posting_days": best_days,
        "disclaimer": "Credential-free estimate from the Arctic archive; a sample, not a census.",
    }
