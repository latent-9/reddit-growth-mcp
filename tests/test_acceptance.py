"""Unit tests for the acceptance reliability ladder (pure, no network)."""

from src.analysis.acceptance import _reliability, _strictness


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


def test_strictness_high_rate_but_low_reliability_is_not_high():
    # 3-of-9 removed reads as 33%, but the sample is too small to trust — the
    # noisy rate must NOT flip strictness to "high" (which would falsely mark a
    # compliant draft "risky"). With no hard gates it drops to "low".
    assert _strictness(0.333, reliability="low", account_gates=[], flair_required=False) == "low"


def test_strictness_high_rate_with_reliability_drives_high():
    assert _strictness(0.333, reliability="high", account_gates=[], flair_required=False) == "high"
    assert _strictness(0.15, reliability="high", account_gates=[], flair_required=False) == "medium"


def test_strictness_hard_rules_win_regardless_of_reliability():
    # Account gates / required flair are exact rules, reliable even on a tiny
    # sample, so they still force "high".
    assert _strictness(0.0, reliability="low", account_gates=[{"type": "age"}], flair_required=False) == "high"
    assert _strictness(0.0, reliability="low", account_gates=[], flair_required=True) == "high"
