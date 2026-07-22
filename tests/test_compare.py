"""Unit tests for the compare module (arctic calls stubbed, no network)."""

import pytest

from src.analysis import compare


def _post(pid, score, comments=0, removed=None, title="A normal project post", created=1_700_000_000):
    return {
        "id": pid,
        "title": title,
        "selftext": "",
        "score": score,
        "num_comments": comments,
        "created_utc": created,
        "url": "https://reddit.com/x",
        "domain": "self.x",
        "is_self": True,
        "link_flair_text": "Show",
        "removed_by_category": removed,
        "permalink": f"/r/x/comments/{pid}/",
    }


@pytest.fixture
def stub_arctic(monkeypatch):
    def _install(posts):
        monkeypatch.setattr(compare.arctic, "fetch_many_posts", lambda *a, **k: posts)

    return _install


def test_profile_safety_and_viral(stub_arctic):
    # 18 live posts (scores 10..180) + 2 mod-removed -> ~10% removal = safe.
    posts = [_post(f"p{i}", (i + 1) * 10, comments=i) for i in range(18)]
    posts += [_post("r1", 5, removed="moderator"), _post("r2", 5, removed="moderator")]
    stub_arctic(posts)

    out = compare.compare_subreddits(["testsub"], sample=50)
    prof = out["ranked"][0]
    assert prof["subreddit"] == "testsub"
    assert prof["removal_rate"] == round(2 / 20, 3)
    assert prof["safety"] == "safe"
    assert prof["viral_ceiling"] > prof["median_score"]  # ceiling above typical
    assert prof["viral_potential"] > 0


def test_recurring_threads_excluded(stub_arctic):
    posts = [_post(f"p{i}", 100, comments=5) for i in range(10)]
    posts += [_post("mega", 9999, comments=9999, title="Daily Discussion Thread")]
    stub_arctic(posts)
    prof = compare.compare_subreddits(["testsub"], sample=50)["ranked"][0]
    assert prof["sampled"] == 10  # megathread dropped


def test_ranking_and_rank_by(stub_arctic, monkeypatch):
    # Two subs: A high ceiling, B steady typical.
    a = [_post(f"a{i}", s) for i, s in enumerate([1, 1, 1, 1, 1, 1, 1, 1, 500, 900])]
    b = [_post(f"b{i}", 30) for i in range(10)]
    calls = {"testA": a, "testB": b}
    monkeypatch.setattr(compare.arctic, "fetch_many_posts", lambda name, *a2, **k: calls[name])

    by_viral = compare.compare_subreddits(["testA", "testB"], rank_by="viral")
    assert by_viral["best_pick"] == "testA"  # high ceiling wins for viral
    by_opp = compare.compare_subreddits(["testA", "testB"], rank_by="opportunity")
    assert by_opp["best_pick"] == "testB"  # steady typical wins for opportunity

    # Growth blends both and is the default.
    default = compare.compare_subreddits(["testA", "testB"])
    assert default["ranked_by"] == "growth"
    assert all("growth_score" in p for p in default["ranked"])


def test_rank_by_insight(monkeypatch):
    # A: high upvotes, few comments; B: modest upvotes, lots of comments.
    a = [_post(f"a{i}", 500, comments=1) for i in range(10)]
    b = [_post(f"b{i}", 30, comments=40) for i in range(10)]
    calls = {"testA": a, "testB": b}
    monkeypatch.setattr(compare.arctic, "fetch_many_posts", lambda name, *a2, **k: calls[name])
    out = compare.compare_subreddits(["testA", "testB"], rank_by="insight")
    assert out["best_pick"] == "testB"  # more discussion wins for insight


def test_empty_input():
    assert "error" in compare.compare_subreddits([])


def test_timeless_post_does_not_zero_velocity(stub_arctic):
    # A single archived post with a missing/zero created_utc must not drag the
    # time span to ~decades and collapse posts_per_day to 0 for an active sub.
    base = 1_700_000_000
    posts = [_post(f"p{i}", 100, comments=5, created=base + i * 3600) for i in range(12)]
    posts.append(_post("timeless", 100, comments=5, created=0))
    stub_arctic(posts)
    prof = compare.compare_subreddits(["testsub"], sample=50)["ranked"][0]
    assert prof["posts_per_day"] > 1  # ~13 posts over ~11h, not 0.0


def test_duplicate_subs_are_deduped(stub_arctic):
    # Same sub via prefix ('r/mcp') or different case ('MCP') is one subreddit on
    # Reddit, so it must be profiled once, keeping the first-seen spelling.
    posts = [_post(f"p{i}", (i + 1) * 10, comments=i) for i in range(10)]
    stub_arctic(posts)
    out = compare.compare_subreddits(["mcp", "r/mcp", "MCP", "mcp"], sample=50)
    assert len(out["ranked"]) == 1
    assert out["ranked"][0]["subreddit"] == "mcp"
