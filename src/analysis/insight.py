"""Discussion-depth ("insight") analysis for a subreddit.

Most tools measure engagement by comment *count*. This measures comment
*quality*: how substantive the discussion is, from a sample of the subreddit's
recent comments. Longer, fewer-but-deeper comments indicate real discussion;
a stream of one-liners indicates drive-by engagement. Credential-free.
"""

from __future__ import annotations

from typing import Any, Dict, List

from . import arctic
from .constants import INSIGHT_HIGH_MEDIAN_CHARS, INSIGHT_LOW_MEDIAN_CHARS, INSIGHT_SUBSTANTIVE_CHARS
from .helpers import clean_subreddit_name, sentiment_counts

_SKIP_BODIES = {"[removed]", "[deleted]", ""}


def _median(values: List[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return round(s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2, 1)


def analyze_insight(
    subreddit_name: str,
    after: str = "3d",
    sample: int = 100,
    ctx: Any = None,
) -> Dict[str, Any]:
    """Estimate how substantive a subreddit's discussion is (creds-free)."""
    name = clean_subreddit_name(subreddit_name)
    try:
        comments = arctic.fetch_recent_comments(name, after=after, limit=sample)
    except arctic.ArcticUnavailable as e:
        return {"error": f"Archive unavailable: {e}", "subreddit": name}

    bodies = [(c.get("body") or "").strip() for c in comments]
    bodies = [b for b in bodies if b not in _SKIP_BODIES]
    if not bodies:
        return {"error": "No comments sampled", "subreddit": name}

    lengths = [len(b) for b in bodies]
    words = [len(b.split()) for b in bodies]
    median_chars = _median(lengths)
    substantive = sum(1 for n in lengths if n >= INSIGHT_SUBSTANTIVE_CHARS)
    substantive_ratio = round(substantive / len(bodies), 2)

    tier = (
        "high"
        if median_chars >= INSIGHT_HIGH_MEDIAN_CHARS
        else "low"
        if median_chars < INSIGHT_LOW_MEDIAN_CHARS
        else "medium"
    )

    # Heuristic sentiment: is the discussion supportive or critical?
    pos_comments = neg_comments = 0
    for b in bodies:
        pos, neg = sentiment_counts(b)
        if pos > neg:
            pos_comments += 1
        elif neg > pos:
            neg_comments += 1
    polarized = pos_comments + neg_comments
    positivity = round(pos_comments / polarized, 2) if polarized else None
    if positivity is None:
        sentiment = "neutral"
    elif positivity >= 0.6:
        sentiment = "supportive"
    elif positivity <= 0.4:
        sentiment = "critical"
    else:
        sentiment = "mixed"

    return {
        "subreddit": name,
        "sampled_comments": len(bodies),
        "insight_tier": tier,
        "median_comment_chars": median_chars,
        "median_comment_words": _median(words),
        "substantive_ratio": substantive_ratio,
        "sentiment": sentiment,
        "positivity_ratio": positivity,
        "note": (
            f"Insight = discussion depth. {substantive_ratio:.0%} of comments are "
            f"substantive (>={INSIGHT_SUBSTANTIVE_CHARS} chars). Credential-free "
            "estimate from a comment sample."
        ),
    }
