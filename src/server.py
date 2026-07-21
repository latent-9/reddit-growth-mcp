"""Reddit Growth MCP — MCP server.

Direct-tool MCP server for analyzing subreddits and post performance:
- find_target_subreddits : discover & rank high-traffic communities by topic
- analyze_subreddit      : estimate a subreddit's reach from public signals
- analyze_acceptance     : rules + removal patterns ("will my post survive?")
- analyze_post_patterns  : what makes posts perform (timing, title, media)
- evaluate_draft         : score a concrete draft for acceptance + engagement
- fetch_posts / fetch_comments / search_subreddit : raw data access
"""

import sys
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional

from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from fastmcp.prompts import Message

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.acceptance import analyze_acceptance as _analyze_acceptance
from src.analysis.compare import compare_subreddits as _compare_subreddits
from src.analysis.draft import evaluate_draft as _evaluate_draft
from src.analysis.draft import evaluate_draft_across as _evaluate_draft_across
from src.analysis.insight import analyze_insight as _analyze_insight
from src.analysis.patterns import analyze_post_patterns as _analyze_post_patterns
from src.analysis.plan import build_growth_plan as _build_growth_plan
from src.analysis.traffic import (
    estimate_activity_archive,
    estimate_subreddit_traffic,
    find_target_subreddits,
)
from src.config import get_reddit_client
from src.resources import register_resources
from src.tools.comments import fetch_submission_with_comments
from src.tools.posts import fetch_multiple_subreddits, fetch_subreddit_posts
from src.tools.search import search_in_subreddit

mcp = FastMCP(
    "Reddit Growth MCP",
    instructions="""
Reddit Growth MCP — grow a Reddit account by posting where you'll be accepted and
seen. Works without Reddit credentials (data from the Arctic Shift archive).

Fast path (recommended):
- growth_plan(subreddits=[...]) — one call: safest strong target, cross-post
  options, its viral recipe, and best posting times.

Step by step:
1. compare_subreddits([...]) — rank by growth/viral/insight, with traffic and a
   safety label so you avoid mod-heavy communities.
2. analyze_post_patterns(subreddit) — the viral recipe: media, flair, title tag,
   keywords, and best times.
3. analyze_acceptance(subreddit) — removal rate and what gets removed.
4. evaluate_draft(subreddit, title, ...) — score a draft 0-100 and get fixes.

Use the reddit_growth prompt to run this whole workflow guided.
All figures are estimates from a sample, not guarantees.
""",
)

# Reddit client is initialized at startup and shared across tools.
reddit = None

_NO_CREDS = {
    "error": "Reddit credentials not configured",
    "hint": "Set REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET in .env. "
    "Tip: analyze_post_patterns and analyze_acceptance already work "
    "without credentials (via the Arctic archive).",
}


def initialize_reddit_client():
    global reddit
    reddit = get_reddit_client()
    register_resources(mcp, reddit)


try:
    initialize_reddit_client()
except Exception as e:  # allow the server to boot without creds for inspection
    # stderr only: on stdio transport stdout carries the JSON-RPC protocol, so
    # any plain text there corrupts the handshake (and fails Glama introspection).
    print(f"WARNING: Reddit client init failed: {e}", file=sys.stderr, flush=True)


# ── Analysis tools ────────────────────────────────────────────────────────


@mcp.tool(
    description="Discover and rank subreddits for given topics by estimated traffic",
    annotations={"readOnlyHint": True},
)
def find_target_subreddits_tool(
    topics: Annotated[List[str], "Topics/keywords, e.g. ['ai','ascii art','repo']"],
    limit_per_topic: Annotated[int, "Search results per topic"] = 15,
    min_subscribers: Annotated[int, "Minimum subscriber count"] = 10000,
    min_daily_visitors: Annotated[int, "Estimated daily-visitor threshold"] = 50000,
    include_nsfw: Annotated[bool, "Include NSFW subreddits"] = False,
    ctx: Context = None,
) -> Dict[str, Any]:
    if reddit is None:
        return _NO_CREDS
    return find_target_subreddits(
        topics,
        reddit,
        limit_per_topic,
        min_subscribers,
        min_daily_visitors,
        include_nsfw,
        ctx,
    )


@mcp.tool(
    description=(
        "Estimate a subreddit's activity (posts/day velocity from the archive; "
        "subscribers and active users too when credentials are present)"
    ),
    annotations={"readOnlyHint": True},
)
def analyze_subreddit(
    subreddit_name: Annotated[str, "Subreddit name (without r/)"],
    sample_size: Annotated[int, "Recent posts to sample for velocity"] = 50,
    ctx: Context = None,
) -> Dict[str, Any]:
    # Falls back to a credential-free velocity estimate from the archive.
    if reddit is None:
        return estimate_activity_archive(subreddit_name, ctx=ctx)
    return estimate_subreddit_traffic(subreddit_name, reddit, sample_size, ctx)


@mcp.tool(
    description=(
        "Analyze a subreddit's removal rate and what tends to get removed (official rules when credentials are present)"
    ),
    annotations={"readOnlyHint": True},
)
def analyze_acceptance(
    subreddit_name: Annotated[str, "Subreddit name (without r/)"],
    sample_size: Annotated[int, "Posts to sample for removal analysis"] = 100,
    use_archive: Annotated[bool, "Use Arctic Shift archive-vs-live diff for accurate removal detection"] = True,
    archive_window: Annotated[str, "Archive lookback window, e.g. 7d/14d/1month"] = "14d",
    ctx: Context = None,
) -> Dict[str, Any]:
    # Works without credentials: removal analysis runs from the Arctic archive.
    # When creds exist, official rules + account gates are added on top.
    return _analyze_acceptance(subreddit_name, reddit, sample_size, use_archive, archive_window, ctx)


@mcp.tool(
    description="Find what makes posts perform: timing, title style, media, flair",
    annotations={"readOnlyHint": True},
)
def analyze_post_patterns(
    subreddit_name: Annotated[str, "Subreddit name (without r/)"],
    listing_type: Annotated[str, "top | hot | new"] = "top",
    time_filter: Annotated[str, "all|year|month|week|day (for 'top')"] = "month",
    limit: Annotated[int, "Posts to sample"] = 100,
    source: Annotated[str, "auto | reddit | archive (archive needs no Reddit creds)"] = "auto",
    metric: Annotated[str, "score | comments | discussion (anti-clickbait) | quality"] = "score",
    ctx: Context = None,
) -> Dict[str, Any]:
    return _analyze_post_patterns(subreddit_name, reddit, listing_type, time_filter, limit, source, metric, ctx)


@mcp.tool(
    description="Evaluate a post draft for acceptance risk and engagement potential",
    annotations={"readOnlyHint": True},
)
def evaluate_draft(
    subreddit_name: Annotated[str, "Target subreddit (without r/)"],
    title: Annotated[str, "Draft post title"],
    body: Annotated[str, "Draft self-text body (optional)"] = "",
    post_type: Annotated[str, "text | image | video | link"] = "text",
    flair: Annotated[Optional[str], "Intended flair (optional)"] = None,
    time_filter: Annotated[str, "Pattern window: all|year|month|week"] = "month",
    ctx: Context = None,
) -> Dict[str, Any]:
    # Runs creds-free (archive removal + patterns); with creds it also checks
    # exact rule compliance.
    return _evaluate_draft(subreddit_name, title, reddit, body, post_type, flair, time_filter, ctx)


@mcp.tool(
    description=(
        "Score one draft across several subreddits and rank by normalized fit "
        "(size-fair percentile) vs raw reach. No creds needed."
    ),
    annotations={"readOnlyHint": True},
)
def evaluate_draft_across(
    subreddits: Annotated[List[str], "Subreddits to compare the draft against"],
    title: Annotated[str, "Draft post title"],
    body: Annotated[str, "Draft self-text body (optional)"] = "",
    post_type: Annotated[str, "text | image | video | link"] = "text",
    flair: Annotated[Optional[str], "Intended flair (optional)"] = None,
    time_filter: Annotated[str, "Pattern window: all|year|month|week"] = "month",
    ctx: Context = None,
) -> Dict[str, Any]:
    return _evaluate_draft_across(subreddits, title, reddit, body, post_type, flair, time_filter, ctx)


@mcp.tool(
    description=(
        "Rank subreddits by growth (typical reach + viral upside, removal-adjusted), "
        "with traffic, discussion, and a safety label. rank_by switches to "
        "viral/opportunity/insight. No creds needed."
    ),
    annotations={"readOnlyHint": True},
)
def compare_subreddits(
    subreddits: Annotated[List[str], "Subreddit names to compare"],
    window: Annotated[str, "Archive lookback, e.g. 30d/60d/90d"] = "60d",
    sample: Annotated[int, "Posts to sample per subreddit"] = 200,
    rank_by: Annotated[str, "growth | viral | opportunity | insight (discussion depth)"] = "growth",
    ctx: Context = None,
) -> Dict[str, Any]:
    return _compare_subreddits(subreddits, window, sample, rank_by, ctx)


@mcp.tool(
    description=(
        "Measure a subreddit's discussion depth (insight): how substantive its "
        "comments are, plus a heuristic sentiment read. No creds needed."
    ),
    annotations={"readOnlyHint": True},
)
def analyze_insight(
    subreddit_name: Annotated[str, "Subreddit name (without r/)"],
    after: Annotated[str, "Comment lookback window, e.g. 3d/7d"] = "3d",
    sample: Annotated[int, "Comments to sample"] = 100,
    ctx: Context = None,
) -> Dict[str, Any]:
    return _analyze_insight(subreddit_name, after, sample, ctx)


@mcp.tool(
    description=(
        "Build a growth plan from candidate subreddits: pick the safest strong one, "
        "list cross-post targets, and return its viral recipe and best posting times. "
        "No credentials needed."
    ),
    annotations={"readOnlyHint": True},
)
def growth_plan(
    subreddits: Annotated[List[str], "Candidate subreddits to plan across"],
    window: Annotated[str, "Archive lookback, e.g. 30d/60d"] = "30d",
    time_filter: Annotated[str, "Pattern window for the recipe: week|month|year"] = "month",
    ctx: Context = None,
) -> Dict[str, Any]:
    return _build_growth_plan(subreddits, reddit, window, time_filter=time_filter, ctx=ctx)


# ── Raw data access tools ─────────────────────────────────────────────────


@mcp.tool(description="Fetch posts from a single subreddit", annotations={"readOnlyHint": True})
def fetch_posts(
    subreddit_name: Annotated[str, "Subreddit name (without r/)"],
    listing_type: Annotated[str, "hot|new|top|rising"] = "hot",
    time_filter: Annotated[Optional[str], "For 'top' listing"] = None,
    limit: Annotated[int, "Number of posts"] = 10,
    ctx: Context = None,
) -> Dict[str, Any]:
    if reddit is None:
        return _NO_CREDS
    return fetch_subreddit_posts(subreddit_name, reddit, listing_type, time_filter, limit, ctx)


@mcp.tool(description="Fetch posts from multiple subreddits at once", annotations={"readOnlyHint": True})
async def fetch_multiple(
    subreddit_names: Annotated[List[str], "Subreddit names (without r/)"],
    listing_type: Annotated[str, "hot|new|top|rising"] = "hot",
    time_filter: Annotated[Optional[str], "For 'top' listing"] = None,
    limit_per_subreddit: Annotated[int, "Posts per subreddit"] = 5,
    ctx: Context = None,
) -> Dict[str, Any]:
    if reddit is None:
        return _NO_CREDS
    return await fetch_multiple_subreddits(subreddit_names, reddit, listing_type, time_filter, limit_per_subreddit, ctx)


@mcp.tool(description="Search posts within a subreddit", annotations={"readOnlyHint": True})
def search_subreddit(
    subreddit_name: Annotated[str, "Subreddit name (without r/)"],
    query: Annotated[str, "Search terms"],
    sort: Annotated[str, "relevance|hot|top|new"] = "relevance",
    time_filter: Annotated[str, "all|year|month|week|day"] = "all",
    limit: Annotated[int, "Max results"] = 10,
    ctx: Context = None,
) -> Dict[str, Any]:
    if reddit is None:
        return _NO_CREDS
    return search_in_subreddit(subreddit_name, query, reddit, sort, time_filter, limit, ctx)


@mcp.tool(description="Fetch a post with its comment tree", annotations={"readOnlyHint": True})
async def fetch_comments(
    submission_id: Annotated[Optional[str], "Reddit post ID"] = None,
    url: Annotated[Optional[str], "Full Reddit post URL"] = None,
    comment_limit: Annotated[int, "Max comments"] = 100,
    comment_sort: Annotated[str, "best|top|new"] = "best",
    ctx: Context = None,
) -> Dict[str, Any]:
    if reddit is None:
        return _NO_CREDS
    return await fetch_submission_with_comments(reddit, submission_id, url, comment_limit, comment_sort, ctx)


@mcp.prompt(
    name="reddit_growth",
    description="Guided workflow to grow a Reddit account: find safe high-traffic subs and craft a post that performs",
)
def reddit_growth(topic: str, subreddits: str = "") -> list[Message]:
    """Guide the assistant through the full growth workflow for a topic.

    Args:
        topic: What the user wants to post about (e.g. "an open-source ASCII MCP tool").
        subreddits: Optional comma-separated candidate subreddits. If empty, ask
                    the user or suggest some based on the topic.
    """
    subs = [s.strip() for s in subreddits.split(",") if s.strip()]
    subs_line = (
        f"Candidate subreddits: {subs}."
        if subs
        else "No subreddits given — suggest 4-6 relevant, active ones for the topic first."
    )
    guide = f"""
You are helping the user grow their Reddit account by posting about: "{topic}".

{subs_line}

Follow this workflow using the Reddit Growth MCP tools (all work without credentials):

1. growth_plan(subreddits=[...]) — get the safest strong target, cross-post
   options, the viral recipe, and best posting times in one call.
2. If the plan's recipe is thin, call analyze_post_patterns(target) for detail
   (media, flair, leading [tag], keywords, timing) and analyze_acceptance(target)
   for removal risk.
3. Draft a post title/body that matches the viral recipe, then call
   evaluate_draft(target, title, ...) and iterate until the acceptance verdict is
   "likely_accepted" and the viral-recipe match is high.

Present a concise plan: which subreddit and why (traffic + safety + reach), the
recommended format/flair/title style with example titles, the best posting time,
and the draft's predicted score. Be honest that figures are estimates.
""".strip()

    return [
        Message(role="user", content=f"Help me grow my Reddit account by posting about: {topic}"),
        Message(role="assistant", content=guide),
    ]


def main():
    """Entry point — runs over stdio transport.

    All startup logging goes to stderr: on stdio transport stdout is the
    JSON-RPC channel, so a stray banner there would break the client handshake
    and Glama's introspection check.
    """
    print("Reddit Growth MCP starting...", file=sys.stderr, flush=True)
    try:
        initialize_reddit_client()
        print("Reddit client ready.", file=sys.stderr, flush=True)
    except Exception as e:
        print(f"WARNING: Reddit client unavailable: {e}", file=sys.stderr, flush=True)
        print("Set REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET in .env", file=sys.stderr, flush=True)
    mcp.run()


if __name__ == "__main__":
    main()
