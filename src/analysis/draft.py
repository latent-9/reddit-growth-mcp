"""Evaluate a concrete post draft against a subreddit.

Combines acceptance analysis (compliance / removal risk) with pattern analysis
(engagement potential) into a single verdict plus actionable fixes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import praw

from .acceptance import analyze_acceptance
from .patterns import analyze_post_patterns
from .helpers import extract_title_features, detect_media_type


def _check_compliance(
    title: str,
    body: str,
    post_type: str,
    flair: Optional[str],
    acceptance: Dict[str, Any],
) -> Dict[str, Any]:
    """Hard rule checks that can outright get a post removed."""
    req = acceptance.get("post_requirements", {}) or {}
    issues: List[str] = []
    warnings: List[str] = []

    if req.get("flair_required") and not flair:
        issues.append("Flair is required but none provided.")
    tmin, tmax = req.get("title_min_length"), req.get("title_max_length")
    if tmin and len(title) < tmin:
        issues.append(f"Title too short ({len(title)} < {tmin}).")
    if tmax and len(title) > tmax:
        issues.append(f"Title too long ({len(title)} > {tmax}).")
    for req_str in req.get("title_required_strings", []) or []:
        if req_str.lower() not in title.lower():
            warnings.append(f"Title may need to contain '{req_str}'.")
    for bad in req.get("title_blacklisted_strings", []) or []:
        if bad.lower() in title.lower():
            issues.append(f"Title contains blacklisted term '{bad}'.")
    if req.get("body_restriction") == "required" and post_type == "text" and not body.strip():
        issues.append("This sub requires a self-text body.")
    if req.get("body_restriction") == "notAllowed" and body.strip():
        warnings.append("This sub disallows self-text bodies; body may be stripped.")
    if acceptance.get("account_gates"):
        warnings.append(
            f"Account gates detected: {[g['raw'] for g in acceptance['account_gates']]}. "
            "Verify your account meets them in THIS sub."
        )

    return {"blocking_issues": issues, "warnings": warnings}


def _score_engagement(title: str, post_type: str, flair: Optional[str],
                      patterns: Dict[str, Any]) -> Dict[str, Any]:
    """Score how well the draft matches this sub's high-performing patterns."""
    tf = extract_title_features(title)
    score = 50
    notes: List[str] = []

    lift = patterns.get("title_signal_lift", {})
    for feature, key in [("is_question", "question_titles"), ("is_list", "list_titles"),
                         ("is_showcase", "showcase_titles"), ("has_number", "has_number")]:
        if tf.get(feature) and lift.get(key, {}).get("lift_pct", 0) > 0:
            score += min(int(lift[key]["lift_pct"] / 5), 15)
            notes.append(f"'{key}' performs +{lift[key]['lift_pct']}% here — good match.")

    # Title length fit.
    bands = {b["band"]: b["avg_score"] for b in patterns.get("title_length_bands", [])}
    if bands:
        best_band = max(bands, key=bands.get)
        cur = ("short (<40)" if tf["char_length"] < 40
               else "medium (40-80)" if tf["char_length"] <= 80 else "long (>80)")
        if cur == best_band:
            score += 10
            notes.append(f"Title length in the best-performing band ({best_band}).")
        else:
            notes.append(f"Best-performing title length is '{best_band}'; yours is '{cur}'.")

    # Media type fit.
    media_ranking = patterns.get("score_by_media_type", [])
    if media_ranking:
        best_media = media_ranking[0]["value"]
        if best_media == post_type:
            score += 10
            notes.append(f"'{post_type}' is the top-performing media type here.")
        else:
            notes.append(f"Top media type here is '{best_media}'; consider it.")

    # Flair fit.
    flair_ranking = patterns.get("score_by_flair", [])
    top_flairs = [f["value"] for f in flair_ranking[:3] if f["value"]]
    if top_flairs:
        if flair in top_flairs:
            score += 5
            notes.append(f"Flair '{flair}' is among top performers.")
        else:
            notes.append(f"High-performing flairs: {top_flairs}.")

    return {"engagement_score": min(score, 100), "notes": notes}


def evaluate_draft(
    subreddit_name: str,
    title: str,
    reddit: praw.Reddit,
    body: str = "",
    post_type: str = "text",
    flair: Optional[str] = None,
    time_filter: str = "month",
    ctx: Any = None,
) -> Dict[str, Any]:
    """Evaluate a draft post for acceptance risk and engagement potential."""
    acceptance = analyze_acceptance(subreddit_name, reddit, sample_size=80, ctx=ctx)
    if "error" in acceptance:
        return {"error": acceptance["error"], "stage": "acceptance"}

    patterns = analyze_post_patterns(subreddit_name, reddit, "top", time_filter, 100, ctx=ctx)
    if "error" in patterns:
        patterns = {}  # engagement scoring degrades gracefully

    compliance = _check_compliance(title, body, post_type, flair, acceptance)
    engagement = _score_engagement(title, post_type, flair, patterns)

    if compliance["blocking_issues"]:
        verdict = "likely_removed"
    elif acceptance.get("strictness") == "high" and compliance["warnings"]:
        verdict = "risky"
    else:
        verdict = "likely_accepted"

    return {
        "subreddit": acceptance["subreddit"],
        "acceptance_verdict": verdict,
        "subreddit_strictness": acceptance.get("strictness"),
        "removal_rate_estimate": acceptance.get("removal_rate_estimate"),
        "blocking_issues": compliance["blocking_issues"],
        "warnings": compliance["warnings"],
        "acceptance_checklist": acceptance.get("acceptance_checklist", []),
        "engagement_score": engagement["engagement_score"],
        "engagement_notes": engagement["notes"],
        "best_posting_hours_utc": patterns.get("best_posting_hours_utc", [])[:3],
        "best_posting_days": patterns.get("best_posting_days", [])[:2],
        "disclaimer": "Guidance from public rules + sampled patterns. Not a guarantee.",
    }
