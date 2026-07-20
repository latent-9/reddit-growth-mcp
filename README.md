# Reddit Analyzer

A toolkit for analyzing subreddits and the patterns behind posts that get
accepted and perform well. It helps you choose the right communities and shape
posts that fit each one, using real data rather than guesswork.

It runs as an MCP server (for use inside Claude, Cursor, and other MCP clients)
and as a standalone command-line tool. Most analysis works without any Reddit
API credentials, because it reads from a public historical archive.

## What it answers

- Which subreddits fit my topic, and how much reach do they have?
- Will my post survive here, or does this community remove a lot of posts?
- What actually performs here: which format, title style, timing, and flair?
- Given a specific draft, how is it likely to do, and how do I improve it?

## Tools

| Tool | Purpose | Needs credentials |
| --- | --- | --- |
| `analyze_post_patterns` | What performs in a sub: timing, media, title style, flair, keywords, by a configurable metric | No |
| `analyze_acceptance` | Removal rate and what tends to get removed; official rules when credentials are present | No |
| `compare_subreddits` | Rank subreddits by viral potential, with traffic (posts/day), discussion, removal risk, and a safety label | No |
| `evaluate_draft` | Predict a draft's performance (0-100) and acceptance risk, with drivers and fixes | No |
| `find_target_subreddits_tool` | Discover and rank subreddits for topics by estimated traffic | Yes |
| `analyze_subreddit` | Estimate a subreddit's reach from public signals | Yes |
| `fetch_posts`, `fetch_multiple`, `search_subreddit`, `fetch_comments` | Raw data access | Yes |

The analysis tools are subreddit-agnostic. They have been exercised on
communities such as `Fedora`, `gnome`, `linux`, `commandline`, `mcp`,
`LocalLLaMA`, and `ClaudeAI`.

## Data sources

- PRAW for live Reddit access (read-only). Requires API credentials.
- Arctic Shift (https://github.com/ArthurHeitmann/arctic_shift), a public
  historical archive and the successor to Pushshift. Requires no credentials.

Removal detection follows the reveddit approach: the archive records what was
posted, and moderator removals are read from that record. When Reddit
credentials are available, `analyze_acceptance` performs an accurate live diff
(archive vs. current Reddit) to resolve ambiguous cases; without credentials it
runs archive-only and flags its confidence.

## Installation

```bash
uv sync
```

Reddit credentials are optional. They unlock the credential-only tools and the
accurate live removal check. Create a "script" application at
https://www.reddit.com/prefs/apps, then:

```bash
cp .env.sample .env
# REDDIT_CLIENT_ID=...
# REDDIT_CLIENT_SECRET=...
# REDDIT_USER_AGENT=RedditAnalyzer/0.1 by u/your_username
```

Without credentials, the pattern, acceptance, comparison, and draft tools still
work via the archive.

## Command-line usage

```bash
uv run python -m src.cli patterns Fedora --time month
uv run python -m src.cli patterns commandline --metric discussion
uv run python -m src.cli acceptance technology
uv run python -m src.cli compare Fedora gnome linux
uv run python -m src.cli draft ClaudeAI --title "I built an ASCII art tool" --type image
```

Add `--json` to any command for raw output.

`patterns` accepts `--metric`:

- `score`: upvotes (reach).
- `comments`: comment volume.
- `discussion`: comments per upvote, a proxy for genuine engagement rather than
  drive-by upvotes.
- `quality`: upvotes damped by a clickbait penalty.

## Use as an MCP server

Register the server once (Claude Code shown):

```bash
claude mcp add reddit-analyzer -- uv run python -m src.server
```

Then ask in natural language, for example "analyze what performs in r/Fedora"
or "will this title get accepted in r/linux?" The client calls the tools.

To run the server directly over stdio:

```bash
uv run python -m src.server
```

## Targeting workflow

To find where to post for growth, `compare_subreddits` reports, per subreddit:

- viral potential (90th-percentile reach adjusted for removal risk) and ceiling,
- posts per day (a credential-free traffic proxy),
- typical discussion (median comments),
- removal rate and a safety label (safe / moderate / strict), so you can avoid
  communities that remove most posts.

A typical flow: `compare` to shortlist safe, high-traffic, high-ceiling subs,
then `patterns` to read the viral recipe, then `evaluate_draft` to score a draft
against it before posting.

## Accuracy and methodology

The tool is built to avoid the common failure modes of naive Reddit analytics.

- Robust central tendency. Categories (media, flair, time) are ranked by the
  median, with the mean shown for reference, so a single viral post cannot crown
  a category.
- Minimum-sample gating. A category or time bucket must contain enough posts to
  be reported as "best". Small buckets are not treated as reliable signals.
- Confidence labelling. Each pattern report states a confidence level based on
  its sample size, and each acceptance report states a reliability level.
- Settled scores. Archived scores stabilise after roughly 36 hours, so analysis
  excludes the most recent two days.
- AutoMod awareness. Posts that were only AutoMod-filtered at capture time are
  treated as uncertain, not confirmed removals, because they are frequently
  approved later. On AutoMod-heavy subreddits this is flagged, and an accurate
  live check requires credentials.
- Anti-clickbait. Clickbait titles are detected (hype phrases, shouted words,
  emoji and punctuation spam), and each report states whether the community
  actually rewards or penalises clickbait, so guidance never pushes you toward
  it. `evaluate_draft` penalises a clickbaity draft only where the sub dislikes
  it.

## Limitations

- Traffic figures are estimates. Reddit does not expose true daily visitor
  counts through its public API.
- Findings are correlations from a sample, not Reddit's ranking algorithm and
  not a guarantee of performance.
- AutoModerator configuration is private. Karma and account-age gates are
  inferred from rule text and require credentials to read.

## Development

```bash
uv run pytest -q
```

The analysis logic lives in `src/analysis/` (traffic, acceptance, patterns,
draft, compare, arctic, helpers). The MCP surface is `src/server.py` and the
CLI is `src/cli.py`.

## License

MIT
