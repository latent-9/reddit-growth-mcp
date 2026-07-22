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
from typing import Any, Dict, List

import praw
from prawcore import Forbidden, NotFound, ResponseException, TooManyRequests

from . import arctic
from .helpers import (
    clean_subreddit_name,
    features_from_arctic,
    safe_mean,
    submission_to_features,
)

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
            rules.append(
                {
                    "name": getattr(rule, "short_name", ""),
                    "description": (getattr(rule, "description", "") or "").strip(),
                    "applies_to": getattr(rule, "kind", "all"),
                }
            )
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
    """Removal sample straight from the Arctic archive — no Reddit creds.

    Classifies confirmed removals vs. survivors vs. AutoMod-filtered (uncertain).
    Because archives snapshot posts at creation, `automod_filtered` here is
    unreliable, so it is returned separately, not counted as a removal.
    """
    archived = arctic.fetch_many_posts(name, after=after, before="2d", target=limit)
    if not archived:
        raise arctic.ArcticUnavailable("no archived posts returned")

    live, mod_removed, filtered = [], [], []
    for post in archived:
        st = features_from_arctic(post)["removal_status"]
        if st == "mod_removed":
            mod_removed.append(features_from_arctic(post))
        elif st == "live":
            live.append(features_from_arctic(post))
        elif st == "filtered":
            filtered.append(features_from_arctic(post))
    return live, mod_removed, filtered


def _sample_via_live_diff(name: str, reddit: praw.Reddit, after: str, limit: int):
    """Accurate reveddit-style sample: archived posts checked against live Reddit.

    The live state resolves the AutoMod-filtered ambiguity — approved posts read
    as live, genuinely removed ones as removed. Needs Reddit credentials.
    """
    archived = arctic.fetch_many_posts(name, after=after, before="2d", target=limit)
    ids = [p.get("id") for p in archived if p.get("id")]
    if not ids:
        raise arctic.ArcticUnavailable("no archived posts returned")

    live_map = {}
    fullnames = [f"t3_{i}" for i in ids]
    for start in range(0, len(fullnames), 100):
        for s in reddit.info(fullnames[start : start + 100]):
            live_map[s.id] = s

    live, mod_removed, filtered = [], [], []
    for pid in ids:
        s = live_map.get(pid)
        if s is None:
            continue
        feats = submission_to_features(s)
        st = feats["removal_status"]
        if st == "mod_removed":
            mod_removed.append(feats)
        elif st == "live":
            live.append(feats)
        elif st == "filtered":
            filtered.append(feats)
    return live, mod_removed, filtered


def _reliability(method: str, sampled: int, filtered_ratio: float) -> str:
    """How much to trust the removal-rate read.

    A tiny sample is unreliable regardless of source, so the `sampled < 10`
    guard is method-independent. Archive-direct additionally can't confirm
    AutoMod-filtered posts, so a heavy filtered share also drags it down.
    Live-diff is authoritative; PRAW listings hide removals (lower bound).
    """
    if sampled < 10 or (method == "archive" and filtered_ratio > 0.3):
        return "low"
    if method.startswith("praw"):
        return "medium"
    return "high"


def _strictness(removal_rate: float, reliability: str, account_gates: list, flair_required: bool) -> str:
    """Classify how strict a sub is, driving the draft's risk verdict.

    A low-confidence removal read (tiny sample) must NOT inflate strictness —
    the checklist already withholds the "strict" warning in that case, so
    letting the same noisy rate flip strictness to "high" (→ "risky" draft
    verdict) would contradict the tool's own confidence caveat. Hard rules
    (account gates, required flair) hold regardless of sample size.
    """
    rate = removal_rate if reliability != "low" else 0.0
    if rate >= 0.3 or account_gates or flair_required:
        return "high"
    if rate >= 0.1:
        return "medium"
    return "low"


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

    # Empirical removal analysis. With creds we run the accurate live diff;
    # without, archive-direct (AutoMod-filtered posts flagged as uncertain).
    live, mod_removed, filtered = [], [], []
    method = "archive"
    try:
        if use_archive and sub is not None:
            try:
                live, mod_removed, filtered = _sample_via_live_diff(name, reddit, archive_window, sample_size)
                method = "archive_live_diff"
            except arctic.ArcticUnavailable:
                live, mod_removed = _sample_via_praw(sub, sample_size)
                method = "praw_listing_fallback"
        elif use_archive:
            try:
                live, mod_removed, filtered = _sample_via_archive(name, archive_window, sample_size)
                method = "archive"
            except arctic.ArcticUnavailable:
                return {
                    "error": "Archive unavailable and no Reddit credentials",
                    "subreddit": name,
                    "hint": "Retry later, or add Reddit credentials for the live source.",
                }
        elif sub is not None:
            live, mod_removed = _sample_via_praw(sub, sample_size)
            method = "praw_listing"
        else:
            return {"error": "use_archive=False requires Reddit credentials", "subreddit": name}
    except (TooManyRequests, ResponseException) as e:
        return {"error": f"Failed to sample posts: {e}", "rules": rules, "post_requirements": requirements}

    sampled = len(live) + len(mod_removed)
    removal_rate = round(len(mod_removed) / sampled, 3) if sampled else 0.0

    # Reliability: a tiny sample is unreliable from any source; archive-direct
    # additionally can't confirm AutoMod-filtered posts, so a heavy filtered
    # share drags it down too. See `_reliability` for the full ladder.
    total_seen = len(live) + len(mod_removed) + len(filtered)
    filtered_ratio = round(len(filtered) / total_seen, 2) if total_seen else 0.0
    heavy_filtering = method == "archive" and filtered_ratio > 0.3
    reliability = _reliability(method, sampled, filtered_ratio)

    # What distinguishes removed posts from survivors?
    def _share(rows: List[Dict[str, Any]], key: str) -> float:
        return round(sum(1 for r in rows if r.get(key)) / len(rows), 2) if rows else 0.0

    contrast = {
        "flair_usage": {"live": _share(live, "flair"), "removed": _share(mod_removed, "flair")},
        "text_posts": {
            # Fraction of live/removed posts that are self-text (not "do they have an id").
            "live": round(sum(1 for r in live if r["media_type"] == "text") / len(live), 2) if live else 0.0,
            "removed": (
                round(sum(1 for r in mod_removed if r["media_type"] == "text") / len(mod_removed), 2)
                if mod_removed
                else 0.0
            ),
        },
        "avg_title_length": {
            "live": safe_mean([r["char_length"] for r in live]),
            "removed": safe_mean([r["char_length"] for r in mod_removed]),
        },
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
    if removal_rate >= 0.3 and reliability != "low":
        checklist.append(f"HIGH removal rate ({removal_rate:.0%}) — this sub is strict; follow rules exactly.")
    if reliability == "low":
        if heavy_filtering:
            checklist.append(
                f"Low-confidence removal read: {filtered_ratio:.0%} of posts are "
                "AutoMod-filtered (may have been approved). Add Reddit credentials "
                "for an accurate live check."
            )
        else:
            checklist.append(
                f"Low-confidence removal read: only {sampled} posts sampled — "
                "too few to estimate the removal rate reliably."
            )

    rules_available = reddit is not None and bool(rules or requirements)
    if not rules_available:
        checklist.append(
            "Official rules not loaded (no Reddit credentials) — checklist is "
            "based on removal patterns only. Add creds for exact rule text."
        )

    strictness = _strictness(removal_rate, reliability, account_gates, requirements.get("flair_required", False))

    if method == "archive_live_diff":
        removal_note = "Removal rate from live diff (Arctic archive vs current Reddit): accurate."
    elif method == "archive":
        removal_note = (
            "Removal rate from the archive; AutoMod-filtered posts are "
            "excluded as uncertain. Add creds for an accurate live check."
        )
    else:
        removal_note = "Removal rate is a LOWER BOUND — PRAW listing hides removed posts."

    return {
        "subreddit": name,
        "strictness": strictness,
        "detection_method": method,
        "reliability": reliability,
        "rules_available": rules_available,
        "removal_rate_estimate": removal_rate,
        "sampled_posts": sampled,
        "mod_removed_count": len(mod_removed),
        "automod_filtered_count": len(filtered),
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
