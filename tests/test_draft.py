"""Unit tests for the data-driven draft predictor (no network)."""

from src.analysis.draft import _check_compliance, _predict_performance

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


def test_compliance_flags_missing_required_flair():
    acceptance = {"post_requirements": {"flair_required": True}, "account_gates": []}
    out = _check_compliance("title", "", "text", None, acceptance)
    assert any("Flair is required" in i for i in out["blocking_issues"])
