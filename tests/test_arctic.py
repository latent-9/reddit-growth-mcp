"""Unit tests for the Arctic archive paging logic (no network)."""

from src.analysis import arctic


def test_fetch_many_posts_ignores_timeless_post_for_cursor(monkeypatch):
    # Page 1 is a full page (100 items) whose last item has no created_utc.
    # The cursor must advance to the oldest *timestamped* post, not break on the
    # zero — otherwise a single timeless post silently truncates pagination.
    page1 = [{"id": f"p{i}", "created_utc": 2000 - i} for i in range(99)]
    page1.append({"id": "timeless"})  # 100th item, no created_utc -> full page
    page2 = [{"id": "q0", "created_utc": 900}]  # short page -> ends paging

    calls = {"n": 0}

    def fake(subreddit, after, before, limit, sort):
        calls["n"] += 1
        return page1 if calls["n"] == 1 else page2

    monkeypatch.setattr(arctic, "fetch_recent_posts", fake)
    out = arctic.fetch_many_posts("x", target=300, delay=0)

    assert calls["n"] == 2  # paging continued past the timeless post
    assert len(out) == 101  # both pages collected, not just the first


def test_fetch_many_posts_stops_when_all_timeless(monkeypatch):
    # If a full page has NO usable timestamps, there is no cursor to advance to,
    # so paging must stop cleanly rather than loop or crash.
    page = [{"id": f"p{i}"} for i in range(100)]  # full page, all timeless

    def fake(subreddit, after, before, limit, sort):
        return page

    monkeypatch.setattr(arctic, "fetch_recent_posts", fake)
    out = arctic.fetch_many_posts("x", target=300, delay=0)

    assert len(out) == 100  # one page, then a clean stop
