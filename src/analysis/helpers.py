"""Shared feature extraction used across the analysis modules.

These helpers turn raw PRAW submissions into flat, comparable feature dicts so
the acceptance / pattern / draft modules can reason about them uniformly.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List

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
    "how",
    "what",
    "why",
    "when",
    "who",
    "which",
    "where",
    "is",
    "are",
    "can",
    "should",
    "does",
    "do",
    "will",
    "would",
)
_LIST_PATTERN = re.compile(r"\b(\d+)\s+(ways|things|tips|reasons|best|top)\b", re.I)
_NUMBER_PATTERN = re.compile(r"\d")
_BRACKET_PATTERN = re.compile(r"[\[\(].+?[\]\)]")
_EMOJI_PATTERN = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]")
_SHOWCASE_PATTERN = re.compile(r"\b(i (made|built|created|drew|designed|coded)|my first|showcase|oc)\b", re.I)


_MEGATHREAD = re.compile(
    r"\b(mega ?thread|daily (discussion|thread|general|chat)|"
    r"weekly (discussion|thread|recap|help|showoff)|monthly (discussion|thread)|"
    r"discussion thread|simple questions|no stupid questions|moronic monday|"
    r"ask me anything|free[- ]?talk|what are you working on|who'?s hiring)\b",
    re.I,
)


def is_recurring_thread(title: str) -> bool:
    """True for recurring official threads (megathreads, AMAs, daily/weekly),
    which carry outsized scores/comments and distort per-post patterns."""
    return bool(_MEGATHREAD.search(title or ""))


_LEADING_TAG = re.compile(r"^\s*\[([^\]]{1,30})\]")


def leading_bracket_tag(title: str):
    """Return the tag inside a leading ``[...]`` if present, else None.

    Many communities prefix titles with a category tag (e.g. ``[KDE]``,
    ``[New Model]``); this extracts it so we can detect that convention.
    """
    m = _LEADING_TAG.match(title or "")
    return m.group(1).strip() if m else None


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
    features["clickbait"] = clickbait_score(title)
    features["recurring"] = is_recurring_thread(title)
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


# --- Clickbait detection -------------------------------------------------
_CLICKBAIT_PHRASES = re.compile(
    r"\b(you won'?t believe|will blow your mind|shocking|insane|jaw[- ]dropping|"
    r"this one (trick|weird)|nobody (talks about|tells you)|mind[- ]?blown|"
    r"gone wrong|must[- ]see|game[- ]changer|the truth about|what happens next|"
    r"i can'?t believe|blew my mind|life[- ]changing|never seen before|"
    r"the secret|one weird trick|doctors hate|you need to see|"
    r"changed my life|this simple trick|will never be the same)\b",
    re.I,
)
_HYPE_WORDS = re.compile(
    r"\b(amazing|incredible|unbelievable|epic|ultimate|"
    r"revolutionary|insane|insanely|crazy|ridiculously|"
    r"mind[- ]blowing|perfect|best ever|100%)\b",
    re.I,
)
_EMOJI = re.compile("[\U0001f300-\U0001faff\U00002600-\U000027bf]")


def clickbait_score(title: str) -> float:
    """Heuristic 0..1 clickbait score for a title (higher = more clickbaity)."""
    t = title or ""
    if not t.strip():
        return 0.0
    points = 0.0
    if _CLICKBAIT_PHRASES.search(t):
        points += 0.5
    points += 0.15 * len(_HYPE_WORDS.findall(t))
    # Shouted words (>=6 chars) — long enough to exclude dev acronyms like
    # MCP/ASCII/API/JSON while still catching BELIEVE/INSANE/SHOCKING.
    caps = sum(1 for w in t.split() if len(w) >= 6 and w.isupper())
    points += 0.15 * caps
    # Excess punctuation and emoji.
    points += 0.15 * len(re.findall(r"[!?]{2,}", t))
    points += 0.10 * len(_EMOJI.findall(t))
    if t.count("!") >= 3:
        points += 0.2
    return round(min(points, 1.0), 2)


def engagement_ratio(score: int, num_comments: int) -> float:
    """Comments per upvote — a proxy for genuine discussion vs drive-by upvotes."""
    return round(num_comments / max(score, 1), 3)


# Lightweight sentiment lexicon (heuristic, not an ML model). Directional only.
_POSITIVE_WORDS = set(
    "great awesome love loved thanks thank nice helpful amazing good excellent "
    "impressive cool works working solved appreciate brilliant perfect best "
    "beautiful clean useful fantastic wonderful glad happy agree agreed based "
    "goated fire underrated congrats congratulations".split()
)
_NEGATIVE_WORDS = set(
    "bad terrible hate hated useless broken wrong awful scam trash garbage stupid "
    "worst disappointing fail failed buggy slow overrated overhyped nonsense "
    "misleading clickbait spam waste dumb annoying ridiculous horrible sucks "
    "cringe disagree wtf".split()
)
_WORD = re.compile(r"[a-z']+")


def sentiment_counts(text: str) -> tuple:
    """Return (positive_hits, negative_hits) for a comment body (lexicon-based)."""
    pos = neg = 0
    for w in _WORD.findall((text or "").lower()):
        if w in _POSITIVE_WORDS:
            pos += 1
        elif w in _NEGATIVE_WORDS:
            neg += 1
    return pos, neg


def metric_value(row: Dict[str, Any], metric: str = "score") -> float:
    """Pluggable performance metric for a post feature row.

    - 'score'      : raw upvotes (reach)
    - 'comments'   : comment count (discussion volume)
    - 'discussion' : comments per upvote (engagement quality, anti-clickbait)
    - 'quality'    : score damped by a clickbait penalty (rewards genuine reach)
    """
    score = row.get("score", 0) or 0
    comments = row.get("num_comments", 0) or 0
    if metric == "comments":
        return comments
    if metric == "discussion":
        return engagement_ratio(score, comments)
    if metric == "quality":
        return round(score * (1 - 0.5 * row.get("clickbait", 0.0)), 1)
    return score


def trimmed_mean(values: List[float], trim: float = 0.1) -> float:
    """Mean after dropping the top and bottom `trim` fraction of values.

    More representative of the "typical high" than a raw mean, which a single
    viral post can dominate.
    """
    if not values:
        return 0.0
    s = sorted(values)
    k = int(len(s) * trim)
    core = s[k : len(s) - k] if len(s) > 2 * k else s
    return round(sum(core) / len(core), 2)


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
    "vs via about into over after before "
    # generic filler that added noise on real data
    "one two now back much rest still also even really way lot all more most some "
    "any only here there im ive dont cant wont thats going gonna want need know like "
    "time day today year years people something anything".split()
)
_TOKEN = re.compile(r"[a-z0-9][a-z0-9'+/-]*")


def winning_keywords(
    rows: List[Dict[str, Any]],
    top_frac: float = 0.25,
    min_count: int = 3,
    n: int = 12,
    score_key: str = "score",
) -> List[Dict[str, Any]]:
    """Words over-represented in high-performing titles vs the rest.

    Splits `rows` (each with 'title' and `score_key`) into a top slice and the
    remainder, then ranks words by how much more often they appear up top.
    Uses additive smoothing so rare words don't produce infinite lift.
    """
    if len(rows) < 8:
        return []
    ranked = sorted(rows, key=lambda r: r.get(score_key, 0), reverse=True)
    k = max(1, int(len(ranked) * top_frac))
    top, rest = ranked[:k], ranked[k:]

    def doc_counts(rs: List[Dict[str, Any]]) -> Dict[str, int]:
        c: Dict[str, int] = {}
        for r in rs:
            words = {
                w
                for w in _TOKEN.findall((r.get("title") or "").lower())
                if w not in _STOPWORDS and len(w) > 2 and "'" not in w
            }
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
        results.append(
            {
                "word": w,
                "count_in_top": ct,
                "top_rate": round(top_rate, 2),
                "lift": round(top_rate / rest_rate, 1),
            }
        )
    results.sort(key=lambda d: d["lift"], reverse=True)
    return results[:n]


def top_counter(pairs: Dict[Any, int], n: int = 3) -> List[Dict[str, Any]]:
    """Return the top-n (key, count) pairs as a list of dicts."""
    ranked = sorted(pairs.items(), key=lambda kv: kv[1], reverse=True)
    return [{"value": k, "count": v} for k, v in ranked[:n]]
