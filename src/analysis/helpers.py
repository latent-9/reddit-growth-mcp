"""Shared feature extraction used across the analysis modules.

These helpers turn raw PRAW submissions into flat, comparable feature dicts so
the acceptance / pattern / draft modules can reason about them uniformly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

# Reddit's removed_by_category values that indicate a *confirmed* moderator or
# admin removal (as opposed to the author deleting their own post).
MOD_REMOVAL_CATEGORIES = {
    "moderator",
    "anti_evil_ops",
    "community_ops",
    "reddit",
    "copyright_takedown",
}
# `automod_filtered` is NOT a confirmed removal: AutoMod routinely filters posts
# into the modqueue and a human approves them minutes later. Archives snapshot
# the post at creation, so this state sticks even for posts that went live.
# Treated as "uncertain" unless a live check proves otherwise.
FILTERED_CATEGORIES = {"automod_filtered"}
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

    Returns one of: "live", "mod_removed", "author_removed", "filtered",
    "unknown". "filtered" means AutoMod-queued at capture time — it may well
    have been approved, so it is uncertain, not a confirmed removal.
    """
    category = getattr(submission, "removed_by_category", None)
    selftext = getattr(submission, "selftext", "") or ""

    if category in MOD_REMOVAL_CATEGORIES:
        return "mod_removed"
    if category in FILTERED_CATEGORIES:
        return "filtered"
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


def features_from_arctic(post: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt an Arctic Shift post dict into the same feature dict as PRAW.

    Wraps the mapping in an attribute-style object so the shared extractors
    (which use getattr) work unchanged.
    """
    obj = SimpleNamespace(
        id=post.get("id"),
        title=post.get("title", "") or "",
        selftext=post.get("selftext", "") or "",
        score=post.get("score", 0) or 0,
        upvote_ratio=post.get("upvote_ratio"),
        num_comments=post.get("num_comments", 0) or 0,
        link_flair_text=post.get("link_flair_text"),
        is_self=post.get("is_self", False),
        is_gallery=post.get("is_gallery", False),
        is_video=post.get("is_video", False),
        over_18=post.get("over_18", False),
        stickied=post.get("stickied", False),
        permalink=post.get("permalink", "") or "",
        created_utc=post.get("created_utc", 0) or 0,
        url=post.get("url", "") or "",
        domain=post.get("domain", "") or "",
        removed_by_category=post.get("removed_by_category"),
    )
    return submission_to_features(obj)


def clean_subreddit_name(name: str) -> str:
    """Strip r/ prefixes and whitespace from a subreddit name."""
    return (name or "").replace("/r/", "").replace("r/", "").strip().lstrip("/")


def safe_mean(values: List[float]) -> float:
    return round(sum(values) / len(values), 2) if values else 0.0


def percentile(sorted_values: List[float], q: float) -> float:
    """Linear-interpolated percentile (q in 0..100) of a pre-sorted list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = (q / 100.0) * (len(sorted_values) - 1)
    lo = int(pos)
    frac = pos - lo
    if lo + 1 >= len(sorted_values):
        return float(sorted_values[-1])
    return round(sorted_values[lo] + frac * (sorted_values[lo + 1] - sorted_values[lo]), 1)


def rank_percentile(sorted_values: List[float], value: float) -> int:
    """Where `value` falls within `sorted_values`, as a 0..100 percentile."""
    if not sorted_values:
        return 0
    below = sum(1 for v in sorted_values if v < value)
    return int(round(100 * below / len(sorted_values)))


_STOPWORDS = set(
    "the a an and or but of to in for on with is are was were be been being this "
    "that these those it its as at by from up down out so if then than too very can "
    "will just my your our their his her you i we they he she them what how why when "
    "who which do does did have has had not no yes new get got make made use using "
    "vs via about into over after before".split()
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9'+/-]*")


def winning_keywords(
    rows: List[Dict[str, Any]],
    top_frac: float = 0.25,
    min_count: int = 3,
    n: int = 12,
) -> List[Dict[str, Any]]:
    """Words over-represented in high-scoring titles vs the rest.

    Splits `rows` (each with 'title' and 'score') into a top slice and the
    remainder, then ranks words by how much more often they appear up top.
    Uses additive smoothing so rare words don't produce infinite lift.
    """
    if len(rows) < 8:
        return []
    ranked = sorted(rows, key=lambda r: r["score"], reverse=True)
    k = max(1, int(len(ranked) * top_frac))
    top, rest = ranked[:k], ranked[k:]

    def doc_counts(rs: List[Dict[str, Any]]) -> Dict[str, int]:
        c: Dict[str, int] = {}
        for r in rs:
            words = {w for w in _TOKEN.findall((r.get("title") or "").lower())
                     if w not in _STOPWORDS and len(w) > 2}
            for w in words:
                c[w] = c.get(w, 0) + 1
        return c

    tc, rc = doc_counts(top), doc_counts(rest)
    n_top, n_rest = len(top), max(len(rest), 1)
    results = []
    for w, ct in tc.items():
        if ct < min_count:
            continue
        top_rate = ct / n_top
        rest_rate = (rc.get(w, 0) + 0.5) / (n_rest + 1)  # smoothed
        results.append({
            "word": w,
            "count_in_top": ct,
            "top_rate": round(top_rate, 2),
            "lift": round(top_rate / rest_rate, 1),
        })
    results.sort(key=lambda d: d["lift"], reverse=True)
    return results[:n]


def top_counter(pairs: Dict[Any, int], n: int = 3) -> List[Dict[str, Any]]:
    """Return the top-n (key, count) pairs as a list of dicts."""
    ranked = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)
    return [{"value": k, "count": v} for k, v in ranked[:n]]
