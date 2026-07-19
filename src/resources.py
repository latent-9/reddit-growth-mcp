"""Reddit Analyzer resources — server info endpoint."""

from typing import Any, Dict

import praw


def register_resources(mcp, reddit: praw.Reddit) -> None:
    """Register the server-info resource with the MCP server."""

    @mcp.resource("reddit://server-info")
    def get_server_info() -> Dict[str, Any]:
        """Server capabilities and usage overview."""
        return {
            "name": "Reddit Analyzer",
            "version": "0.1.0",
            "description": (
                "Analyze subreddits and post performance: find high-traffic "
                "communities, learn each sub's acceptance rules, and evaluate "
                "drafts before posting."
            ),
            "tools": {
                "find_target_subreddits_tool": "Discover & rank subreddits by estimated traffic (needs creds)",
                "analyze_subreddit": "Estimate a subreddit's reach from public signals (needs creds)",
                "analyze_acceptance": "Removal rate + what gets nuked; rules when creds present (creds-free)",
                "analyze_post_patterns": "What makes posts perform: timing, title, media, keywords (creds-free)",
                "compare_subreddits": "Rank subs by opportunity (reach vs removal risk) (creds-free)",
                "evaluate_draft": "Predict a draft's performance (0-100) + acceptance risk (creds-free)",
                "fetch_posts": "Fetch posts from a subreddit (needs creds)",
                "fetch_multiple": "Fetch posts from multiple subreddits (needs creds)",
                "search_subreddit": "Search within a subreddit (needs creds)",
                "fetch_comments": "Fetch a post with its comment tree (needs creds)",
            },
            "recommended_workflow": [
                "compare_subreddits([...])  # pick the best sub",
                "analyze_acceptance(subreddit)  # learn what survives",
                "analyze_post_patterns(subreddit)  # learn what performs",
                "evaluate_draft(subreddit, title, ...)  # score your draft",
            ],
            "data_notes": [
                "Traffic figures are estimates; Reddit hides true visitor counts.",
                "Removal rates are a lower bound (API hides some removed posts).",
                "AutoMod config is private; account gates are inferred from rules.",
            ],
            "authentication": {"type": "Application-only OAuth", "scope": "Read-only"},
        }
