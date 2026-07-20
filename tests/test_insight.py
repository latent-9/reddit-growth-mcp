"""Unit tests for the insight module (arctic stubbed, no network)."""

from src.analysis import insight


def _comments(bodies):
    return [{"body": b, "score": 1} for b in bodies]


def test_high_insight(monkeypatch):
    long_bodies = ["word " * 60 for _ in range(10)]  # ~300 chars each
    monkeypatch.setattr(insight.arctic, "fetch_recent_comments", lambda *a, **k: _comments(long_bodies))
    out = insight.analyze_insight("deepdiscussion")
    assert out["insight_tier"] == "high"
    assert out["substantive_ratio"] == 1.0


def test_low_insight(monkeypatch):
    monkeypatch.setattr(
        insight.arctic, "fetch_recent_comments", lambda *a, **k: _comments(["nice", "lol", "+1", "this"])
    )
    out = insight.analyze_insight("oneliners")
    assert out["insight_tier"] == "low"
    assert out["substantive_ratio"] == 0.0


def test_skips_removed_and_empty(monkeypatch):
    bodies = ["[removed]", "[deleted]", "", "A genuinely substantive comment " * 8]
    monkeypatch.setattr(insight.arctic, "fetch_recent_comments", lambda *a, **k: _comments(bodies))
    out = insight.analyze_insight("mixed")
    assert out["sampled_comments"] == 1  # only the real comment counts


def test_no_comments(monkeypatch):
    monkeypatch.setattr(insight.arctic, "fetch_recent_comments", lambda *a, **k: [])
    assert "error" in insight.analyze_insight("empty")


def test_sentiment_supportive(monkeypatch):
    bodies = ["this is great and helpful, thanks"] * 6 + ["neutral statement here"] * 2
    monkeypatch.setattr(insight.arctic, "fetch_recent_comments", lambda *a, **k: _comments(bodies))
    out = insight.analyze_insight("nice")
    assert out["sentiment"] == "supportive"
    assert out["positivity_ratio"] == 1.0


def test_sentiment_critical(monkeypatch):
    bodies = ["this is terrible and useless, broken"] * 6 + ["ok"] * 2
    monkeypatch.setattr(insight.arctic, "fetch_recent_comments", lambda *a, **k: _comments(bodies))
    out = insight.analyze_insight("mean")
    assert out["sentiment"] == "critical"
