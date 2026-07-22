"""Unit tests for the acceptance reliability ladder (pure, no network)."""

from src.analysis.acceptance import _reliability


def test_small_sample_is_low_for_every_method():
    # A tiny sample is unreliable regardless of source — the guard is not
    # gated behind method == "archive" (the bug this fixes).
    for method in ("archive", "archive_live_diff", "praw_listing", "praw_listing_fallback"):
        assert _reliability(method, sampled=5, filtered_ratio=0.0) == "low"


def test_live_diff_with_enough_sample_is_high():
    assert _reliability("archive_live_diff", sampled=40, filtered_ratio=0.0) == "high"
    # Live-diff resolves AutoMod ambiguity, so a high filtered_ratio doesn't apply.
    assert _reliability("archive_live_diff", sampled=40, filtered_ratio=0.9) == "high"


def test_plain_archive_heavy_filtering_is_low_else_high():
    assert _reliability("archive", sampled=40, filtered_ratio=0.5) == "low"
    assert _reliability("archive", sampled=40, filtered_ratio=0.0) == "high"
    # Boundary: > 0.3 trips it, exactly 0.3 does not.
    assert _reliability("archive", sampled=40, filtered_ratio=0.31) == "low"
    assert _reliability("archive", sampled=40, filtered_ratio=0.30) == "high"


def test_praw_listing_is_medium_when_well_sampled():
    assert _reliability("praw_listing", sampled=40, filtered_ratio=0.0) == "medium"
    assert _reliability("praw_listing_fallback", sampled=40, filtered_ratio=0.0) == "medium"


def test_small_sample_boundary():
    assert _reliability("archive_live_diff", sampled=9, filtered_ratio=0.0) == "low"
    assert _reliability("archive_live_diff", sampled=10, filtered_ratio=0.0) == "high"
