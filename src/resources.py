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
                "find_target_subreddits_tool": "Discover & rank subreddits by estimated traffic",
                "analyze_subreddit": "Estimate a subreddit's reach from public signals",
                "analyze_acceptance": "Rules + removal patterns (will my post survive?)",
                "analyze_post_patterns": "What makes posts perform (timing, title, media)",
                "evaluate_draft": "Score a draft for acceptance risk + engagement",
                "fetch_posts": "Fetch posts from a subreddit",
                "fetch_multiple": "Fetch posts from multiple subreddits",
                "search_subreddit": "Search within a subreddit",
                "fetch_comments": "Fetch a post with its comment tree",
            },
            "recommended_workflow": [
                "find_target_subreddits_tool(topics=[...])",
                "analyze_acceptance(subreddit)",
                "analyze_post_patterns(subreddit)",
                "evaluate_draft(subreddit, title, ...)",
            ],
            "data_notes": [
                "Traffic figures are estimates; Reddit hides true visitor counts.",
                "Removal rates are a lower bound (API hides some removed posts).",
                "AutoMod config is private; account gates are inferred from rules.",
            ],
            "authentication": {"type": "Application-only OAuth", "scope": "Read-only"},
        }
