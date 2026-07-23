"""Reddit Growth MCP resources — server info endpoint."""

import json
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

import praw

try:
    # Report the real installed version so server-info never drifts from
    # pyproject (dist name = [project].name). The Glama/Docker/pipx deploy has
    # the package installed, so this resolves to the true version.
    _VERSION = _pkg_version("reddit-growth-mcp")
except PackageNotFoundError:
    _VERSION = "0.2.1"  # fallback for source-tree runs (e.g. pytest) with no install


def register_resources(mcp, reddit: praw.Reddit) -> None:
    """Register the server-info resource with the MCP server."""

    @mcp.resource("reddit://server-info", mime_type="application/json")
    def get_server_info() -> str:
        """Server capabilities and usage overview."""
        # FastMCP resources must return str/bytes, not a dict (it raises
        # otherwise), so serialize; mime_type advertises it as JSON.
        return json.dumps({
            "name": "Reddit Growth MCP",
            "version": _VERSION,
            "description": (
                "Analyze subreddits and post performance: find high-traffic "
                "communities, learn each sub's acceptance rules, and evaluate "
                "drafts before posting."
            ),
            "tools": {
                "growth_plan": "One call: safest target + cross-posts + viral recipe + timing (creds-free)",
                "compare_subreddits": "Rank subs by growth/viral/insight, with traffic + safety (creds-free)",
                "analyze_insight": "Discussion depth + heuristic sentiment of a sub's comments (creds-free)",
                "analyze_post_patterns": "What makes posts perform: timing, title, media, keywords (creds-free)",
                "analyze_acceptance": "Removal rate + what gets nuked; rules when creds present (creds-free)",
                "evaluate_draft": "Predict a draft's performance (0-100) + acceptance risk (creds-free)",
                "analyze_subreddit": "Estimate a subreddit's activity (posts/day) (creds-free)",
                "find_target_subreddits_tool": "Discover & rank subreddits by estimated traffic (needs creds)",
                "fetch_posts": "Fetch posts from a subreddit (needs creds)",
                "fetch_multiple": "Fetch posts from multiple subreddits (needs creds)",
                "search_subreddit": "Search within a subreddit (needs creds)",
                "fetch_comments": "Fetch a post with its comment tree (needs creds)",
            },
            "prompts": {
                "reddit_growth": "Guided workflow to grow an account: find a safe sub and craft a post that performs",
            },
            "recommended_workflow": [
                "growth_plan([...])  # one-shot: where + what + when",
                "analyze_post_patterns(subreddit)  # detail the viral recipe",
                "evaluate_draft(subreddit, title, ...)  # score your draft",
            ],
            "data_notes": [
                "Traffic figures are estimates; Reddit hides true visitor counts.",
                "Removal rates are a lower bound (API hides some removed posts).",
                "AutoMod config is private; account gates are inferred from rules.",
            ],
            "authentication": {"type": "Application-only OAuth", "scope": "Read-only"},
        })
