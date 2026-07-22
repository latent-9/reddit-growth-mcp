"""Unit tests for CLI presentation helpers (no network required)."""

from src.cli import _content_style


def test_content_style_maps_plain_media():
    # No signal words: fall back to the media-type description.
    assert _content_style("image", None, None, None) == "images (screenshots / visuals)"
    assert _content_style("link", None, None, None) == "linked articles / pages"


def test_content_style_reads_signal_words():
    assert _content_style("image", "Meme", None, None) == "memes / humor"
    assert _content_style("link", "News", None, None) == "news / announcements"
    assert _content_style("image", "Showcase", None, None) == "showcases / projects"
    assert _content_style("text", "Question", None, None) == "questions / help"


def test_content_style_ignores_substring_false_positives():
    # 'rocket'/'protocol'/'vscode' must NOT trip 'oc' → showcases, and 'show'
    # must NOT trip 'how' → questions. These are ordinary winning-keyword tokens.
    assert _content_style("image", None, ["rocket", "protocol", "docker"], None) == "images (screenshots / visuals)"
    assert _content_style("link", None, ["showreel", "vscode"], None) == "linked articles / pages"


def test_content_style_matches_whole_word_and_suffixes():
    # Whole word 'oc' (original content) still matches; suffixes still match via prefix.
    assert _content_style("image", "OC", None, None) == "showcases / projects"
    assert _content_style("link", None, ["announcements"], None) == "news / announcements"
