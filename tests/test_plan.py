"""Unit tests for the growth planner (sub-analyses stubbed, no network)."""

from src.analysis import plan


def _stub(monkeypatch, ranked, patterns=None, insight=None):
    monkeypatch.setattr(plan, "compare_subreddits", lambda *a, **k: {"ranked": ranked})
    monkeypatch.setattr(plan, "analyze_post_patterns", lambda *a, **k: patterns or {})
    monkeypatch.setattr(plan, "analyze_insight", lambda *a, **k: insight or {})


def _sub(name, safety="safe", low=False, growth=100):
    return {
        "subreddit": name,
        "safety": safety,
        "low_confidence": low,
        "growth_score": growth,
        "viral_potential": growth * 2,
        "posts_per_day": 30,
        "median_comments": 10,
        "removal_rate": 0.1,
    }


def test_picks_safest_strong_and_avoids_strict(monkeypatch):
    ranked = [_sub("Strict", safety="strict", growth=999), _sub("Safe", growth=50)]
    _stub(monkeypatch, ranked, insight={"insight_tier": "high", "substantive_ratio": 0.6})
    out = plan.build_growth_plan(["Strict", "Safe"])
    assert out["target"]["subreddit"] == "Safe"  # strict sub avoided despite higher growth
    assert "Strict" in out["avoided"]
    assert out["target"]["insight_tier"] == "high"


def test_includes_recipe_and_crossposts(monkeypatch):
    ranked = [_sub("Main"), _sub("Alt")]
    patterns = {
        "viral_profile": {"available": True, "recipe": {"media_type": {"value": "video"}}},
        "best_posting_hours_utc": [{"hour_utc": 15}],
        "best_posting_days": [{"day": "Friday"}],
    }
    _stub(monkeypatch, ranked, patterns=patterns, insight={"insight_tier": "medium", "substantive_ratio": 0.4})
    out = plan.build_growth_plan(["Main", "Alt"])
    assert out["recipe"]["media_type"]["value"] == "video"
    assert [p["subreddit"] for p in out["also_consider"]] == ["Alt"]


def test_error_when_no_data(monkeypatch):
    monkeypatch.setattr(plan, "compare_subreddits", lambda *a, **k: {"error": "no data"})
    assert "error" in plan.build_growth_plan(["x"])


def test_target_not_listed_in_own_avoided_when_all_low_confidence(monkeypatch):
    # Niche/low-volume subs are routinely all low_confidence (compare sets it on
    # considered < 10). The fallback target must NOT appear in its own avoid list,
    # and a caveat must flag that it's the best of a bad lot.
    ranked = [_sub("SmallA", low=True, growth=800), _sub("SmallB", low=True, growth=400)]
    _stub(monkeypatch, ranked)
    out = plan.build_growth_plan(["SmallA", "SmallB"])
    assert out["target"]["subreddit"] == "SmallA"
    assert "SmallA" not in out["avoided"]  # no self-contradiction
    assert out["avoided"] == ["SmallB"]  # the other bad option is still avoided
    assert out["target"]["caveat"]  # fallback flagged as tentative


def test_clean_pick_has_no_caveat(monkeypatch):
    # When an eligible (safe, well-sampled) candidate exists, no caveat is set.
    ranked = [_sub("Safe", growth=100), _sub("Strict", safety="strict", growth=999)]
    _stub(monkeypatch, ranked)
    out = plan.build_growth_plan(["Safe", "Strict"])
    assert out["target"]["subreddit"] == "Safe"
    assert out["target"]["caveat"] is None
    assert out["avoided"] == ["Strict"]
