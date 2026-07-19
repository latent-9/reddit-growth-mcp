# Reddit Analyzer

An MCP server for analyzing subreddits and reverse-engineering the patterns
behind posts that get **accepted** and **perform well** — so you can pick the
right high-traffic communities and post content that fits.

## Tools

| Tool | What it answers |
|------|-----------------|
| `find_target_subreddits_tool` | Which subreddits fit my topics, ranked by estimated traffic? |
| `analyze_subreddit` | How big/active is this community? |
| `analyze_acceptance` | Will my post survive here? (rules, karma/age gates, real removal rate) |
| `analyze_post_patterns` | What makes posts perform? (timing, title style, media, flair) |
| `evaluate_draft` | Score a specific draft for acceptance risk + engagement |
| `fetch_posts` · `fetch_multiple` · `search_subreddit` · `fetch_comments` | Raw data access |

Works for any community with real activity — not just AI. Tested on tech subs
like `Fedora`, `gnome`, `linux`, as well as `ClaudeAI`, `MachineLearning`, etc.

## Data sources

- **[PRAW](https://praw.readthedocs.io/)** — live Reddit (read-only). Needs API credentials.
- **[Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift)** — historical archive (Pushshift successor). No credentials needed.

`analyze_acceptance` detects moderator removals the reveddit way: it diffs the
Arctic archive (posts that *existed*) against live Reddit, revealing removed
posts that PRAW's listing hides. `analyze_post_patterns` can run entirely from
the archive (`source="archive"`), so it works **without any Reddit credentials**.

## Setup

```bash
uv sync
```

Optional (unlocks the live tools and accurate removal detection) — create a
"script" app at https://www.reddit.com/prefs/apps, then:

```bash
cp .env.sample .env
# REDDIT_CLIENT_ID=...
# REDDIT_CLIENT_SECRET=...
# REDDIT_USER_AGENT=RedditAnalyzer/0.1 by u/your_username
```

Without credentials, `analyze_post_patterns` still works via the archive.

## Use it from an MCP client

Register the server once (Claude Code shown):

```bash
claude mcp add reddit-analyzer -- uv run python -m src.server
```

Then just ask, e.g. *"analyze what performs in r/Fedora"* or *"will this title
get accepted in r/linux?"* — the client calls the tools for you.

## Run standalone

```bash
uv run python -m src.server   # starts the MCP server on stdio
```

## Notes & limits

- Traffic figures are **estimates** — Reddit hides true daily visitors publicly.
- Archive scores settle after ~36h; pattern analysis skips the last ~2 days.
- AutoMod config is private; karma/age gates are inferred from rule text.

## License

MIT
