"""Acceptance analysis: "will my post survive in this subreddit?"

Three signal sources, from most to least authoritative:
1. Official subreddit rules (`subreddit.rules`).
2. Structured post requirements (`subreddit.post_requirements()`): flair,
   title/body constraints, domain allow/deny lists.
3. Empirical removal analysis: sample recent posts, see what got mod-removed
   vs. survived, and correlate features. (AutoMod config is private, so this
   is inference, not ground truth.)
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

import praw
from prawcore import NotFound, Forbidden, TooManyRequests, ResponseException

from .helpers import (
    clean_subreddit_name,
    submission_to_features,
    features_from_arctic,
    safe_mean,
)
from . import arctic

# Phrases in rule text that hint at account-based gates (karma / age).
_KARMA_PATTERN = re.compile(r"(\d[\d,]*)\s*\+?\s*(comment|post|combined|total)?\s*karma", re.I)
_AGE_PATTERN = re.compile(r"(\d+)\s*(day|week|month|year)s?\s*(old|age)", re.I)


def _extract_account_gates(rules_text: str) -> List[Dict[str, Any]]:
    """Best-effort detection of karma / account-age gates from rule text."""
    gates: List[Dict[str, Any]] = []
    for m in _KARMA_PATTERN.finditer(rules_text):
        gates.append({"type": "karma", "value": m.group(1), "raw": m.group(0).strip()})
    for m in _AGE_PATTERN.finditer(rules_text):
        gates.append({"type": "account_age", "value": f"{m.group(1)} {m.group(2)}", "raw": m.group(0).strip()})
    return gates


def _load_rules(sub: praw.reddit.Subreddit) -> List[Dict[str, Any]]:
    rules = []
    try:
        for rule in sub.rules:
            rules.append({
                "name": getattr(rule, "short_name", ""),
                "description": (getattr(rule, "description", "") or "").strip(),
                "applies_to": getattr(rule, "kind", "all"),
            })
    except (ResponseException, TooManyRequests):
        pass
    return rules


def _load_post_requirements(sub: praw.reddit.Subreddit) -> Dict[str, Any]:
    try:
        req = sub.post_requirements()
    except (ResponseException, TooManyRequests, Exception):
        return {}
    return {
        "flair_required": req.get("is_flair_required", False),
        "title_min_length": req.get("title_text_min_length"),
        "title_max_length": req.get("title_text_max_length"),
        "title_required_strings": req.get("title_required_strings", []),
        "title_blacklisted_strings": req.get("title_blacklisted_strings", []),
        "body_restriction": req.get("body_restriction_policy", "none"),
        "body_blacklisted_strings": req.get("body_blacklisted_strings", []),
        "domain_whitelist": req.get("domain_whitelist", []),
        "domain_blacklist": req.get("domain_blacklist", []),
        "guidelines": (req.get("guidelines_text") or "").strip() or None,
    }


def _sample_via_praw(sub, sample_size: int):
    """Removal sample from PRAW `.new()`. Lower bound: removed posts are hidden."""
    live, mod_removed = [], []
    for post in sub.new(limit=sample_size):
        feats = submission_to_features(post)
        if feats["removal_status"] == "mod_removed":
            mod_removed.append(feats)
        elif feats["removal_status"] == "live":
            live.append(feats)
    return live, mod_removed


def _sample_via_archive(name: str, after: str, limit: int):
    """Removal sample straight from the Arctic archive — no Reddit creds needed.

    Arctic re-checks posts after creation, so its `removed_by_category` /
    `[removed]` selftext already flags moderator removals that PRAW's `.new()`
    listing hides entirely. This is the reveddit signal without a live diff.
    """
    archived = arctic.fetch_recent_posts(name, after=after, before="1d",
                                         limit=limit, sort="desc")
    if not archived:
        raise arctic.ArcticUnavailable("no archived posts returned")

    live, mod_removed = [], []
    for post in archived:
        feats = features_from_arctic(post)
        if feats["removal_status"] == "mod_removed":
            mod_removed.append(feats)
        elif feats["removal_status"] == "live":
            live.append(feats)
    return live, mod_removed


def analyze_acceptance(
    subreddit_name: str,
    reddit: praw.Reddit = None,
    sample_size: int = 100,
    use_archive: bool = True,
    archive_window: str = "14d",
    ctx: Any = None,
) -> Dict[str, Any]:
    """Analyze how strict a subreddit is and what tends to get removed.

    Removal analysis runs from the Arctic archive and needs NO Reddit
    credentials. When a Reddit client is provided, the official rules,
    post requirements, and account gates are added on top.
    """
    name = clean_subreddit_name(subreddit_name)

    # Official rules / requirements need OAuth; only load them if we have a
    # Reddit client. Removal analysis below works without one.
    rules: List[Dict[str, Any]] = []
    requirements: Dict[str, Any] = {}
    account_gates: List[Dict[str, Any]] = []
    sub = None
    if reddit is not None:
        try:
            sub = reddit.subreddit(name)
            _ = sub.display_name  # force existence check
            rules = _load_rules(sub)
            requirements = _load_post_requirements(sub)
            rules_text = " ".join(r["name"] + " " + r["description"] for r in rules)
            account_gates = _extract_account_gates(rules_text)
        except NotFound:
            return {"error": f"Subreddit r/{name} not found", "status_code": 404}
        except Forbidden:
            return {"error": f"r/{name} is private or banned", "status_code": 403}
        except (TooManyRequests, ResponseException) as e:
            return {"error": f"Reddit API error: {e}"}

    # Empirical removal analysis. Archive-direct is preferred (accurate + no
    # creds); PRAW listing is a lower-bound fallback when a client exists.
    live, mod_removed = [], []
    method = "archive"
    try:
        if use_archive:
            try:
                live, mod_removed = _sample_via_archive(name, archive_window, sample_size)
                method = "archive"
            except arctic.ArcticUnavailable:
                if sub is None:
                    return {"error": "Archive unavailable and no Reddit credentials",
                            "subreddit": name,
                            "hint": "Retry later, or add Reddit credentials for the live source."}
                live, mod_removed = _sample_via_praw(sub, sample_size)
                method = "praw_listing_fallback"
        elif sub is not None:
            live, mod_removed = _sample_via_praw(sub, sample_size)
            method = "praw_listing"
        else:
            return {"error": "use_archive=False requires Reddit credentials",
                    "subreddit": name}
    except (TooManyRequests, ResponseException) as e:
        return {"error": f"Failed to sample posts: {e}", "rules": rules,
                "post_requirements": requirements}

    sampled = len(live) + len(mod_removed)
    removal_rate = round(len(mod_removed) / sampled, 3) if sampled else 0.0

    # What distinguishes removed posts from survivors?
    def _share(rows: List[Dict[str, Any]], key: str) -> float:
        return round(sum(1 for r in rows if r.get(key)) / len(rows), 2) if rows else 0.0

    contrast = {
        "flair_usage": {"live": _share(live, "flair"), "removed": _share(mod_removed, "flair")},
        "text_posts": {
            "live": _share([r for r in live if r["media_type"] == "text"], "id") if live else 0.0,
            "removed": _share([r for r in mod_removed if r["media_type"] == "text"], "id") if mod_removed else 0.0,
        },
        "avg_title_length": {"live": safe_mean([r["char_length"] for r in live]),
                             "removed": safe_mean([r["char_length"] for r in mod_removed])},
    }
    live_media = Counter(r["media_type"] for r in live)

    # Build a plain-language acceptance checklist.
    checklist: List[str] = []
    if requirements.get("flair_required"):
        checklist.append("Flair is REQUIRED — always set a post flair.")
    if requirements.get("title_min_length"):
        checklist.append(f"Title must be at least {requirements['title_min_length']} chars.")
    if requirements.get("title_max_length"):
        checklist.append(f"Title must be at most {requirements['title_max_length']} chars.")
    if requirements.get("title_required_strings"):
        checklist.append(f"Title must contain one of: {requirements['title_required_strings']}.")
    if requirements.get("domain_whitelist"):
        checklist.append(f"Links only allowed from: {requirements['domain_whitelist']}.")
    if requirements.get("body_restriction") == "required":
        checklist.append("Self-text body is REQUIRED.")
    if requirements.get("body_restriction") == "notAllowed":
        checklist.append("Self-text body is NOT allowed (link-only sub).")
    for gate in account_gates:
        checklist.append(f"Account gate detected ({gate['type']}): {gate['raw']}.")
    if live_media:
        top_media = live_media.most_common(1)[0][0]
        checklist.append(f"Most surviving posts are '{top_media}' type — favor that format.")
    if removal_rate >= 0.3:
        checklist.append(f"HIGH removal rate ({removal_rate:.0%}) — this sub is strict; follow rules exactly.")

    rules_available = reddit is not None and bool(rules or requirements)
    if not rules_available:
        checklist.append(
            "Official rules not loaded (no Reddit credentials) — checklist is "
            "based on removal patterns only. Add creds for exact rule text."
        )

    strictness = ("high" if removal_rate >= 0.3 or account_gates or requirements.get("flair_required")
                  else "medium" if removal_rate >= 0.1 else "low")

    if method.startswith("archive"):
        removal_note = "Removal rate from the Arctic archive: accurate, includes posts PRAW's listing hides."
    else:
        removal_note = "Removal rate is a LOWER BOUND — PRAW listing hides removed posts."

    return {
        "subreddit": name,
        "strictness": strictness,
        "detection_method": method,
        "rules_available": rules_available,
        "removal_rate_estimate": removal_rate,
        "sampled_posts": sampled,
        "mod_removed_count": len(mod_removed),
        "account_gates": account_gates,
        "post_requirements": requirements,
        "rules": rules,
        "removed_vs_live_contrast": contrast,
        "surviving_media_mix": dict(live_media),
        "acceptance_checklist": checklist,
        "disclaimer": (
            f"{removal_note} AutoMod config is private; account gates are "
            "inferred from rule text (requires credentials)."
        ),
    }
