"""Unit tests for the robust pattern-aggregation helpers (no network)."""

from src.analysis.patterns import (
    _bool_lift,
    _clickbait_effect,
    _group_stats,
    _median,
    analyze_post_patterns,
)


class _FakeSub:
    """Records the time_filter praw would receive; returns an empty listing."""

    def __init__(self, rec):
        self.rec = rec

    def top(self, time_filter=None, limit=None):
        self.rec["time_filter"] = time_filter
        return []

    def hot(self, limit=None):
        return []

    def new(self, limit=None):
        return []


class _FakeReddit:
    def __init__(self, rec):
        self.rec = rec

    def subreddit(self, name):
        return _FakeSub(self.rec)


def test_invalid_time_filter_is_normalized_not_raised():
    # A caller passing a window-style string ("30d") must not reach praw's .top()
    # (which raises ValueError) — it's normalized to the default first.
    rec = {}
    out = analyze_post_patterns("x", reddit=_FakeReddit(rec), source="reddit", time_filter="30d")
    assert rec["time_filter"] == "month"  # normalized, praw never sees "30d"
    assert "error" in out  # empty listing → structured error, no crash


def _rows(pairs, key="media_type"):
    """Build feature-like rows from (category, perf) pairs."""
    return [{key: cat, "_perf": perf} for cat, perf in pairs]


def test_median():
    assert _median([]) == 0.0
    assert _median([5]) == 5.0
    assert _median([1, 2, 3]) == 2.0
    assert _median([1, 2, 3, 4]) == 2.5


def test_group_stats_min_sample_gating():
    # 'image' has 4 samples; 'video' only 1 -> video is filtered out (min_n=3).
    rows = _rows([("image", 10), ("image", 20), ("image", 30), ("image", 100), ("video", 999)])
    out = _group_stats(rows, "media_type", "_perf", min_n=3)
    values = [b["value"] for b in out]
    assert "image" in values
    assert "video" not in values  # one lucky post can't crown a category


def test_group_stats_ranks_by_median_not_mean():
    # A: median 10 but one 1000 outlier; B: steady median 20.
    rows = _rows([("A", 10), ("A", 10), ("A", 10), ("A", 1000), ("B", 20), ("B", 20), ("B", 20), ("B", 20)])
    out = _group_stats(rows, "media_type", "_perf", min_n=3)
    assert out[0]["value"] == "B"  # steady beats outlier-inflated mean
    a = next(b for b in out if b["value"] == "A")
    assert a["mean"] > a["median"]  # mean is inflated, median is robust


def test_bool_lift_reliability_flag():
    rows = [{"is_question": True, "_perf": 5} for _ in range(2)]
    rows += [{"is_question": False, "_perf": 10} for _ in range(10)]
    out = _bool_lift(rows, "is_question", "_perf", min_n=5)
    assert out["reliable"] is False  # only 2 'with' samples

    rows2 = [{"is_question": True, "_perf": 5} for _ in range(8)]
    rows2 += [{"is_question": False, "_perf": 10} for _ in range(8)]
    assert _bool_lift(rows2, "is_question", "_perf", min_n=5)["reliable"] is True


def test_bool_lift_near_zero_baseline_is_capped():
    # Both groups cleared the sample floor, but the 'without' group barely scores
    # (avg ~0.33). The raw ratio would explode (+90000%); the report must cap the
    # figure. Display sanity comes from the cap, not from flagging it unreliable.
    rows = [{"has_number": True, "_perf": 300} for _ in range(6)]
    rows += [{"has_number": False, "_perf": 0} for _ in range(5)]
    rows += [{"has_number": False, "_perf": 2} for _ in range(1)]  # off_avg ≈ 0.33
    out = _bool_lift(rows, "has_number", "_perf", min_n=5)
    assert out["lift_pct"] <= 300.0  # capped, no absurd +90000%


def test_bool_lift_ratio_metric_below_one_stays_reliable():
    # For ratio metrics like 'discussion' (comments/upvote), values are legitimately
    # < 1. A well-sampled signal must NOT be flagged unreliable just for a small
    # baseline — reliability is about sample count, not magnitude.
    rows = [{"is_question": True, "_perf": 0.8} for _ in range(20)]
    rows += [{"is_question": False, "_perf": 0.4} for _ in range(20)]
    out = _bool_lift(rows, "is_question", "_perf", min_n=5)
    assert out["reliable"] is True
    assert out["lift_pct"] == 100.0  # 0.8 vs 0.4 → +100%, a real signal


def test_clickbait_effect_verdict():
    baity = [{"clickbait": 0.6, "_perf": 5} for _ in range(5)]
    clean = [{"clickbait": 0.0, "_perf": 50} for _ in range(5)]
    out = _clickbait_effect(baity + clean, "_perf")
    assert out["verdict"] == "clickbait_penalized"

    few = [{"clickbait": 0.0, "_perf": 10} for _ in range(5)]
    assert _clickbait_effect(few, "_perf")["verdict"] == "too_few_clickbait_samples"
