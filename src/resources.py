"""Reddit Growth MCP resources — server info endpoint."""

from typing import Any, Dict

import praw


def register_resources(mcp, reddit: praw.Reddit) -> None:
    """Register the server-info resource with the MCP server."""

    @mcp.resource("reddit://server-info")
    def get_server_info() -> Dict[str, Any]:
        """Server capabilities and usage overview."""
        return {
            "name": "Reddit Growth MCP",
            "version": "0.2.0",
            "description": (
                "Analyze subreddits and post performance: find high-traffic "
                "communities, learn each sub's acceptance rules, and evaluate "
                "drafts before posting."
            ),
            "tools": {
                "growth_plan": "One call: safest target + cross-posts + viral recipe + timing (creds-free)",
                "compare_subreddits": "Rank subs by growth/viral/insight, with traffic + safety (creds-free)",
                "analyze_insight": "Discussion depth: how substantive a sub's comments are (creds-free)",
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
        }
