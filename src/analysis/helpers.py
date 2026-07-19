"""Shared feature extraction used across the analysis modules.

These helpers turn raw PRAW submissions into flat, comparable feature dicts so
the acceptance / pattern / draft modules can reason about them uniformly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# Reddit's removed_by_category values that indicate a *moderator/admin* action
# (as opposed to the author deleting their own post).
MOD_REMOVAL_CATEGORIES = {
    "moderator",
    "automod_filtered",
    "anti_evil_ops",
    "community_ops",
    "reddit",
    "copyright_takedown",
}
AUTHOR_REMOVAL_CATEGORIES = {"deleted", "author"}

_QUESTION_STARTERS = (
    "how", "what", "why", "when", "who", "which", "where",
    "is", "are", "can", "should", "does", "do", "will", "would",
)
_LIST_PATTERN = re.compile(r"\b(\d+)\s+(ways|things|tips|reasons|best|top)\b", re.I)
_NUMBER_PATTERN = re.compile(r"\d")
_BRACKET_PATTERN = re.compile(r"[\[\(].+?[\]\)]")
_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]"
)
_SHOWCASE_PATTERN = re.compile(
    r"\b(i (made|built|created|drew|designed|coded)|my first|showcase|oc)\b", re.I
)


def classify_removal(submission: Any) -> str:
    """Classify how a post was removed, best-effort without mod permissions.

    Returns one of: "live", "mod_removed", "author_removed", "unknown".
    Note: removed posts are only partially exposed by the public API, so
    mod-removal rates derived from this are a *lower bound*.
    """
    category = getattr(submission, "removed_by_category", None)
    selftext = getattr(submission, "selftext", "") or ""

    if category in MOD_REMOVAL_CATEGORIES:
        return "mod_removed"
    if category in AUTHOR_REMOVAL_CATEGORIES:
        return "author_removed"
    if selftext == "[removed]":
        return "mod_removed"
    if selftext == "[deleted]":
        return "author_removed"
    if category is None:
        return "live"
    return "unknown"


def detect_media_type(submission: Any) -> str:
    """Coarse media classification: text, image, video, gallery, link."""
    if getattr(submission, "is_self", False):
        return "text"
    if getattr(submission, "is_gallery", False):
        return "gallery"

    url = (getattr(submission, "url", "") or "").lower()
    domain = (getattr(submission, "domain", "") or "").lower()

    if getattr(submission, "is_video", False) or "v.redd.it" in domain:
        return "video"
    if any(host in domain for host in ("youtube.com", "youtu.be", "vimeo.com")):
        return "video_external"
    if "i.redd.it" in domain or url.endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
        return "image"
    if "imgur.com" in domain:
        return "image"
    return "link"


def extract_title_features(title: str) -> Dict[str, Any]:
    """Extract structural signals from a post title."""
    title = title or ""
    lowered = title.lower().strip()
    words = title.split()
    first_word = words[0].lower().rstrip("'?s") if words else ""

    return {
        "char_length": len(title),
        "word_count": len(words),
        "is_question": lowered.endswith("?") or first_word in _QUESTION_STARTERS,
        "is_list": bool(_LIST_PATTERN.search(title)),
        "is_showcase": bool(_SHOWCASE_PATTERN.search(title)),
        "has_number": bool(_NUMBER_PATTERN.search(title)),
        "has_brackets": bool(_BRACKET_PATTERN.search(title)),
        "has_emoji": bool(_EMOJI_PATTERN.search(title)),
        "is_all_caps": title.isupper() and len(title) > 3,
    }


def extract_time_features(created_utc: float) -> Dict[str, Any]:
    """Weekday / hour features from a UTC timestamp."""
    dt = datetime.fromtimestamp(created_utc, tz=timezone.utc)
    return {
        "hour_utc": dt.hour,
        "weekday": dt.weekday(),  # 0 = Monday
        "weekday_name": dt.strftime("%A"),
        "iso_date": dt.strftime("%Y-%m-%d"),
    }


def submission_to_features(submission: Any) -> Dict[str, Any]:
    """Flatten a PRAW submission into a single feature dict."""
    title = getattr(submission, "title", "") or ""
    created = float(getattr(submission, "created_utc", 0) or 0)

    features: Dict[str, Any] = {
        "id": getattr(submission, "id", None),
        "title": title,
        "score": int(getattr(submission, "score", 0) or 0),
        "upvote_ratio": getattr(submission, "upvote_ratio", None),
        "num_comments": int(getattr(submission, "num_comments", 0) or 0),
        "flair": getattr(submission, "link_flair_text", None),
        "media_type": detect_media_type(submission),
        "removal_status": classify_removal(submission),
        "over_18": bool(getattr(submission, "over_18", False)),
        "stickied": bool(getattr(submission, "stickied", False)),
        "permalink": f"https://reddit.com{getattr(submission, 'permalink', '')}",
        "created_utc": created,
    }
    features.update(extract_title_features(title))
    if created:
        features.update(extract_time_features(created))
    return features


def clean_subreddit_name(name: str) -> str:
    """Strip r/ prefixes and whitespace from a subreddit name."""
    return (name or "").replace("/r/", "").replace("r/", "").strip().lstrip("/")


def safe_mean(values: List[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def top_counter(pairs: Dict[Any, int], n: int = 3) -> List[Dict[str, Any]]:
    """Return the top-n (key, count) pairs as a list of dicts."""
    ranked = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)
    return [{"value": k, "count": v} for k, v in ranked[:n]]
