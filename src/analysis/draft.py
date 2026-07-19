"""Evaluate a concrete post draft against a subreddit.

Combines acceptance analysis (compliance / removal risk) with pattern analysis
(engagement potential) into a single verdict plus actionable fixes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import praw

from .acceptance import analyze_acceptance
from .patterns import analyze_post_patterns
from .helpers import extract_title_features


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


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


def _band_of(char_length: int) -> str:
    return ("short (<40)" if char_length < 40
            else "medium (40-80)" if char_length <= 80 else "long (>80)")


def _predict_performance(title: str, post_type: str, flair: Optional[str],
                         patterns: Dict[str, Any]) -> Dict[str, Any]:
    """Predict a draft's performance from the sub's own score distribution.

    Starts at the sub's average score, applies data-derived multipliers for
    media type, title length band, title signals, flair, and winning keywords,
    then maps the projected score onto the sample's percentile distribution to
    yield a 0-100 performance score. Every factor is reported as a driver.
    """
    tf = extract_title_features(title)
    base = patterns.get("score_stats", {}).get("avg", 0) or 0
    overall = base if base > 0 else 1.0
    drivers: List[Dict[str, Any]] = []
    suggestions: List[str] = []
    mult = 1.0

    def ratio_to(avg: float) -> float:
        return _clamp((avg or 0) / overall, 0.2, 4.0) if overall else 1.0

    # Media type.
    media = {m["value"]: m["avg_score"] for m in patterns.get("score_by_media_type", [])}
    if media:
        best_media = max(media, key=media.get)
        if post_type in media:
            r = ratio_to(media[post_type]); mult *= r
            drivers.append({"factor": f"media={post_type}", "impact": f"×{round(r,2)}"})
        if best_media != post_type:
            suggestions.append(f"Top media type here is '{best_media}' (avg {media[best_media]}); yours is '{post_type}'.")

    # Title length band.
    bands = {b["band"]: b["avg_score"] for b in patterns.get("title_length_bands", [])}
    if bands:
        cur = _band_of(tf["char_length"])
        best_band = max(bands, key=bands.get)
        if cur in bands:
            r = ratio_to(bands[cur]); mult *= r
            drivers.append({"factor": f"title_len={cur}", "impact": f"×{round(r,2)}"})
        if best_band != cur:
            suggestions.append(f"Best title length is '{best_band}'; yours is '{cur}'.")

    # Title signals (question/list/showcase/number/emoji).
    lift = patterns.get("title_signal_lift", {})
    for feat, key in [("is_question", "question_titles"), ("is_list", "list_titles"),
                      ("is_showcase", "showcase_titles"), ("has_number", "has_number"),
                      ("has_emoji", "has_emoji")]:
        if tf.get(feat):
            pct = lift.get(key, {}).get("lift_pct", 0)
            r = _clamp(1 + pct / 100.0, 0.5, 2.0); mult *= r
            drivers.append({"factor": key, "impact": f"×{round(r,2)} ({pct:+.0f}%)"})
    # Suggest a high-lift signal the draft is missing.
    for key, feat in [("has_number", "has_number"), ("showcase_titles", "is_showcase")]:
        if not tf.get(feat) and lift.get(key, {}).get("lift_pct", 0) > 30:
            suggestions.append(f"Titles with '{key}' score {lift[key]['lift_pct']:+.0f}% here — consider adding.")

    # Flair.
    flairs = {f["value"]: f["avg_score"] for f in patterns.get("score_by_flair", []) if f["value"]}
    if flairs:
        if flair in flairs:
            r = ratio_to(flairs[flair]); mult *= r
            drivers.append({"factor": f"flair={flair}", "impact": f"×{round(r,2)}"})
        else:
            top3 = sorted(flairs, key=flairs.get, reverse=True)[:3]
            suggestions.append(f"High-performing flairs: {top3}.")

    # Winning keywords present in the title.
    kws = {k["word"] for k in patterns.get("winning_keywords", [])}
    matched = [w for w in kws if w in title.lower()]
    if matched:
        r = _clamp(1 + 0.1 * len(matched), 1.0, 1.4); mult *= r
        drivers.append({"factor": f"keywords={matched}", "impact": f"×{round(r,2)}"})

    projected = round(overall * mult, 1)

    # Map projected score onto the sample distribution → 0-100.
    pct = patterns.get("score_percentiles", {})
    if pct:
        pts = sorted((int(q), v) for q, v in pct.items())
        performance = 0
        for q, v in pts:
            if projected >= v:
                performance = q
        # interpolate above the top breakpoint
        if projected >= pts[-1][1]:
            performance = min(99, pts[-1][0] + 4)
    else:
        performance = 50

    band = ("viral" if performance >= 90 else "strong" if performance >= 70
            else "average" if performance >= 40 else "weak")

    return {
        "performance_score": performance,
        "projected_score": projected,
        "performance_band": band,
        "baseline_avg_score": overall,
        "drivers": drivers,
        "suggestions": suggestions,
    }


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

    patterns = analyze_post_patterns(subreddit_name, reddit, "top", time_filter, 200, ctx=ctx)
    if "error" in patterns:
        patterns = {}  # prediction degrades gracefully

    compliance = _check_compliance(title, body, post_type, flair, acceptance)
    prediction = _predict_performance(title, post_type, flair, patterns)

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
        "performance_score": prediction["performance_score"],
        "performance_band": prediction["performance_band"],
        "projected_score": prediction["projected_score"],
        "baseline_avg_score": prediction["baseline_avg_score"],
        "score_drivers": prediction["drivers"],
        "suggestions": prediction["suggestions"],
        "best_posting_hours_utc": patterns.get("best_posting_hours_utc", [])[:3],
        "best_posting_days": patterns.get("best_posting_days", [])[:2],
        "disclaimer": "Prediction from public rules + sampled patterns. An estimate, not a guarantee.",
    }
