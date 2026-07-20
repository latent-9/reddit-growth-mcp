"""Unit tests for feature-extraction helpers (no network required)."""

from types import SimpleNamespace

from src.analysis.helpers import (
    classify_removal,
    detect_media_type,
    extract_title_features,
    extract_time_features,
    clean_subreddit_name,
    submission_to_features,
    features_from_arctic,
    winning_keywords,
    percentile,
    rank_percentile,
    clickbait_score,
    engagement_ratio,
    metric_value,
)


def _sub(**kwargs):
    """Build a fake submission with sane defaults."""
    defaults = dict(
        id="abc", title="Hello world", selftext="", score=10, upvote_ratio=0.9,
        num_comments=3, link_flair_text=None, is_self=True, is_gallery=False,
        is_video=False, over_18=False, stickied=False, permalink="/r/x/comments/abc/",
        created_utc=1_700_000_000.0, url="https://reddit.com/x", domain="self.x",
        removed_by_category=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_clean_subreddit_name():
    assert clean_subreddit_name("r/Python") == "Python"
    assert clean_subreddit_name("/r/aiArt ") == "aiArt"
    assert clean_subreddit_name("MachineLearning") == "MachineLearning"


def test_classify_removal():
    assert classify_removal(_sub(removed_by_category=None)) == "live"
    assert classify_removal(_sub(removed_by_category="moderator")) == "mod_removed"
    assert classify_removal(_sub(removed_by_category="deleted")) == "author_removed"
    assert classify_removal(_sub(selftext="[removed]")) == "mod_removed"
    # AutoMod-filtered is uncertain (often approved later), not a confirmed removal.
    assert classify_removal(_sub(removed_by_category="automod_filtered")) == "filtered"


def test_detect_media_type():
    assert detect_media_type(_sub(is_self=True)) == "text"
    assert detect_media_type(_sub(is_self=False, domain="i.redd.it", url="x.png")) == "image"
    assert detect_media_type(_sub(is_self=False, is_video=True, domain="v.redd.it")) == "video"
    assert detect_media_type(_sub(is_self=False, domain="youtube.com")) == "video_external"
    assert detect_media_type(_sub(is_self=False, domain="example.com", url="https://example.com")) == "link"


def test_extract_title_features():
    q = extract_title_features("How do I build an ASCII renderer?")
    assert q["is_question"] is True
    assert q["word_count"] == 7

    lst = extract_title_features("5 tips for prompting Claude")
    assert lst["is_list"] is True
    assert lst["has_number"] is True

    show = extract_title_features("I made a tiny AI art tool")
    assert show["is_showcase"] is True


def test_extract_time_features():
    tf = extract_time_features(1_700_000_000.0)
    assert 0 <= tf["hour_utc"] <= 23
    assert tf["weekday_name"] in {
        "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
    }


def test_submission_to_features_shape():
    feats = submission_to_features(_sub(title="Best AI repo of 2025", score=42))
    assert feats["score"] == 42
    assert feats["media_type"] == "text"
    assert feats["removal_status"] == "live"
    assert "char_length" in feats and "hour_utc" in feats


def test_features_from_arctic():
    # Arctic returns plain dicts (with some fields absent, e.g. is_gallery).
    post = {
        "id": "xyz", "title": "Fedora Silverblue setup notes",
        "selftext": "steps...", "score": 120, "num_comments": 8,
        "created_utc": 1_700_000_000, "url": "https://reddit.com/r/Fedora/x",
        "domain": "self.Fedora", "is_self": True, "link_flair_text": "Guide",
        "removed_by_category": None, "permalink": "/r/Fedora/comments/xyz/",
    }
    feats = features_from_arctic(post)
    assert feats["score"] == 120
    assert feats["media_type"] == "text"
    assert feats["flair"] == "Guide"
    assert feats["removal_status"] == "live"
    assert feats["is_question"] is False


def test_winning_keywords():
    # "ascii" appears only in high-scoring titles → should rank as a winner.
    rows = [{"title": f"ascii art showcase {i}", "score": 500 - i} for i in range(6)]
    rows += [{"title": f"random support question {i}", "score": i} for i in range(6)]
    kws = winning_keywords(rows, top_frac=0.5, min_count=2)
    words = [k["word"] for k in kws]
    assert "ascii" in words
    top = next(k for k in kws if k["word"] == "ascii")
    assert top["lift"] > 1.0


def test_winning_keywords_small_sample_returns_empty():
    assert winning_keywords([{"title": "hi", "score": 1}]) == []


def test_percentile():
    vals = [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    assert percentile(vals, 50) == 50.0
    assert percentile(vals, 0) == 0.0
    assert percentile(vals, 100) == 100.0
    assert percentile([], 50) == 0.0


def test_rank_percentile():
    vals = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert rank_percentile(vals, 1) == 0      # nothing below the minimum
    assert rank_percentile(vals, 6) == 50     # half below
    assert rank_percentile(vals, 100) == 100  # everything below


def test_clickbait_score():
    assert clickbait_score("A calm honest title about Fedora") == 0.0
    assert clickbait_score("You won't BELIEVE this INSANE trick!!!") >= 0.5
    assert clickbait_score("My new ASCII tool 🔥🔥🔥") > 0
    # Clean dev title stays low.
    assert clickbait_score("Open-source MCP server for ASCII art") < 0.3


def test_engagement_ratio():
    assert engagement_ratio(100, 50) == 0.5
    assert engagement_ratio(0, 5) == 5.0   # guards divide-by-zero


def test_metric_value():
    row = {"score": 100, "num_comments": 20, "clickbait": 0.6}
    assert metric_value(row, "score") == 100
    assert metric_value(row, "comments") == 20
    assert metric_value(row, "discussion") == 0.2
    assert metric_value(row, "quality") == 70.0   # 100 * (1 - 0.5*0.6)
