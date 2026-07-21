"""Unit tests for the data-driven draft predictor (no network)."""

from src.analysis import draft
from src.analysis.draft import _check_compliance, _predict_performance, evaluate_draft_across

# A synthetic patterns report where image posts and 'showcase' titles win big.
PATTERNS = {
    "score_stats": {"mean": 100, "median": 40, "max": 2000},
    "score_percentiles": {25: 20, 50: 40, 75: 120, 90: 400, 95: 800},
    "score_by_media_type": [
        {"value": "image", "median": 200, "mean": 300, "count": 30},
        {"value": "text", "median": 20, "mean": 40, "count": 50},
    ],
    "title_length_bands": [
        {"value": "short (<40)", "median": 40, "mean": 60, "count": 20},
        {"value": "medium (40-80)", "median": 120, "mean": 180, "count": 40},
        {"value": "long (>80)", "median": 30, "mean": 50, "count": 20},
    ],
    "title_signal_lift": {
        "showcase_titles": {"lift_pct": 80, "sample_with": 12},
        "has_number": {"lift_pct": 40, "sample_with": 20},
        "question_titles": {"lift_pct": -50, "sample_with": 15},
        "list_titles": {"lift_pct": 0, "sample_with": 0},
        "has_emoji": {"lift_pct": 0, "sample_with": 0},
    },
    "score_by_flair": [
        {"value": "Showcase", "median": 300, "mean": 400, "count": 12},
        {"value": "Help", "median": 5, "mean": 10, "count": 20},
    ],
    "winning_keywords": [{"word": "ascii"}, {"word": "generator"}],
    "clickbait_effect": {"verdict": "clickbait_neutral", "lift_pct": 0},
}


def test_strong_draft_scores_high():
    # Image + winning title band + showcase phrasing + top flair + keyword.
    res = _predict_performance(
        title="I made an ascii art generator for the terminal",  # medium length, showcase, keyword
        post_type="image",
        flair="Showcase",
        patterns=PATTERNS,
    )
    assert res["performance_score"] >= 70
    assert res["performance_band"] in {"strong", "viral"}
    assert res["projected_score"] > PATTERNS["score_stats"]["mean"]


def test_weak_draft_scores_low_and_suggests():
    # Text (weak media) + question title (negative lift) + no flair.
    res = _predict_performance(
        title="how do i fix this?",
        post_type="text",
        flair=None,
        patterns=PATTERNS,
    )
    assert res["performance_score"] <= 60
    assert any("image" in s for s in res["suggestions"])  # nudge toward top media


def test_predict_degrades_without_patterns():
    res = _predict_performance("anything", "text", None, patterns={})
    assert "performance_score" in res


def test_degenerate_distribution_not_labeled_viral():
    # A mostly-removed sub: the whole score distribution sits near zero, so a
    # top-percentile score is still ~1 upvote. That must not read as viral.
    dead = {
        "score_stats": {"mean": 1, "median": 1, "max": 2},
        "score_percentiles": {25: 0, 50: 1, 75: 1, 90: 1, 95: 2},
        "score_by_media_type": [{"value": "text", "median": 1, "mean": 1, "count": 10}],
    }
    res = _predict_performance("check out my thing", "text", None, patterns=dead)
    assert res["projected_score"] < 5
    assert res["performance_band"] == "weak"
    assert res["performance_score"] <= 35


def test_small_sub_top_percentile_not_labeled_viral():
    # A low-engagement sub: a top-percentile post still projects only ~6 upvotes.
    # That must not read as viral/strong, however high its percentile.
    small = {
        "score_stats": {"mean": 4, "median": 2, "max": 10},
        "score_percentiles": {25: 1, 50: 2, 75: 4, 90: 6, 95: 8},
        "score_by_media_type": [{"value": "image", "median": 5, "mean": 6, "count": 10}],
    }
    res = _predict_performance("my project in 2026", "image", None, patterns=small)
    assert res["projected_score"] < 25  # only a handful of upvotes
    assert res["performance_band"] not in {"viral", "strong"}


def test_compliance_flags_missing_required_flair():
    acceptance = {"post_requirements": {"flair_required": True}, "account_gates": []}
    out = _check_compliance("title", "", "text", None, acceptance)
    assert any("Flair is required" in i for i in out["blocking_issues"])


def test_evaluate_draft_across_ranks_by_fit_not_reach(monkeypatch):
    # Small sub: post is top-percentile (fit 95) but low raw reach (30).
    # Big sub: post is average (fit 40) but high raw reach (500).
    canned = {
        "Small": {
            "subreddit": "Small",
            "performance_score": 95,
            "performance_band": "viral",
            "projected_score": 30,
            "acceptance_verdict": "likely_accepted",
            "removal_rate_estimate": 0.05,
            "viral_alignment": {"alignment_pct": 80},
        },
        "Big": {
            "subreddit": "Big",
            "performance_score": 40,
            "performance_band": "average",
            "projected_score": 500,
            "acceptance_verdict": "likely_accepted",
            "removal_rate_estimate": 0.1,
            "viral_alignment": {"alignment_pct": 20},
        },
    }
    monkeypatch.setattr(draft, "evaluate_draft", lambda name, *a, **k: canned[name])
    out = evaluate_draft_across(["Small", "Big"], "a title")
    assert out["best_fit"] == "Small"  # size-fair fit prefers the small sub
    assert out["most_reach"] == "Big"  # raw reach prefers the big sub
