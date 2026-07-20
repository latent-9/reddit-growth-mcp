# Reddit Analyzer

An MCP server for analyzing subreddits and reverse-engineering the patterns
behind posts that get **accepted** and **perform well** — so you can pick the
right high-traffic communities and post content that fits.

## Tools

| Tool | What it answers |
|------|-----------------|
| `find_target_subreddits_tool` | Which subreddits fit my topics, ranked by estimated traffic? |
| `analyze_subreddit` | How big/active is this community? |
| `analyze_acceptance` | Will my post survive here? (real removal rate + what gets nuked; rules/gates when creds present) |
| `analyze_post_patterns` | What makes posts perform? (timing, title, media, flair, keywords) — pick a metric: upvotes / comments / discussion (anti-clickbait) / quality |
| `compare_subreddits` | Which of these subs gives the best shot? (reach vs removal risk) |
| `evaluate_draft` | Predict a draft's performance (0–100) + acceptance risk, with drivers & fixes |
| `fetch_posts` · `fetch_multiple` · `search_subreddit` · `fetch_comments` | Raw data access |

Works for any community with real activity — not just AI. Tested on tech subs
like `Fedora`, `gnome`, `linux`, as well as `ClaudeAI`, `MachineLearning`, etc.

## Data sources

- **[PRAW](https://praw.readthedocs.io/)** — live Reddit (read-only). Needs API credentials.
- **[Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift)** — historical archive (Pushshift successor). No credentials needed.

**`analyze_post_patterns` and `analyze_acceptance` work without any Reddit
credentials** — both run from the Arctic archive, which records moderator
removals directly (the reveddit signal without a live diff). Adding Reddit
credentials layers on the official rule text, post requirements, and traffic
metrics that the archive doesn't carry.

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

## CLI (no MCP client needed)

Run analyses directly in the terminal — works without Reddit credentials:

```bash
uv run python -m src.cli patterns Fedora --time month     # what performs here
uv run python -m src.cli acceptance technology            # removal rate + what gets nuked
uv run python -m src.cli compare Fedora gnome linux        # rank subs by opportunity
uv run python -m src.cli draft ClaudeAI --title "I built an ASCII art tool"
```

Add `--json` to any command for raw output. `patterns` takes `--metric`:
`score` (upvotes), `comments`, `discussion` (comments/upvote — anti-clickbait),
or `quality` (upvotes damped by a clickbait penalty). Every report also states
whether the sub actually *rewards* clickbait, so the guidance never pushes you
toward it.

## Notes & limits

- Traffic figures are **estimates** — Reddit hides true daily visitors publicly.
- Archive scores settle after ~36h; pattern analysis skips the last ~2 days.
- AutoMod config is private; karma/age gates are inferred from rule text.

## License

MIT
