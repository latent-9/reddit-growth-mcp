# Reddit Analyzer

A toolkit for analyzing subreddits and reverse-engineering the patterns behind posts that perform well.

## Goals

- **Subreddit analysis** — measure traffic and activity: subscribers, active users, posting cadence, engagement rates, and dominant content types. Surface which communities are worth targeting.
- **Post-pattern analysis** — sample top/hot posts from a subreddit and learn what correlates with high scores: title length and phrasing, posting time, media type, flair, and upvote ratio. Reddit's ranking is not public, so patterns are inferred from real data.

## Status

Early rework. The Reddit access layer (PRAW-based fetch/search over posts and comments) is inherited and reused; the analysis tools are being built on top of it.

## Stack

- Python 3.11+
- [PRAW](https://praw.readthedocs.io/) for Reddit API access (read-only)
- [FastMCP](https://github.com/jlowin/fastmcp) server layer

## Setup

```bash
uv sync
cp .env.sample .env   # add your Reddit API credentials
```

Required environment variables:

```
REDDIT_CLIENT_ID=...
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=RedditAnalyzer/0.1 by u/your_username
```

Get credentials at https://www.reddit.com/prefs/apps (create a "script" app).

## Run

```bash
uv run python -m src.server
```

## License

MIT
