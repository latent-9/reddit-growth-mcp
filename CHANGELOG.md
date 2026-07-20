# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
semantic versioning.

## [Unreleased]

### Viral optimization
- Viral DNA profile: isolate the top-decile posts and report their shared
  recipe (media, flair, time block, title traits, keywords) and which traits are
  over-represented versus the rest.
- `compare_subreddits` ranks by viral potential (90th-percentile reach adjusted
  for removal risk) by default, so high-ceiling communities surface for a viral
  goal; `rank_by` switches to typical-reach opportunity.
- `evaluate_draft` reports a viral-recipe alignment score and the exact traits a
  draft is missing to match what goes viral in the sub.

### Added
- `evaluate_draft_across` (`fit`): score one draft across subreddits and rank by
  size-normalized fit (percentile within each sub) versus raw reach, so subs of
  different sizes compare fairly.
- `analyze_insight`: measure a subreddit's discussion depth (median comment
  length and substantive ratio) rather than just comment count, to find where
  thoughtful discussion happens. Credential-free; exposed as an MCP tool and the
  CLI `insight` command.
- `growth_plan` MCP tool and `reddit_growth` guided prompt for the full workflow
  in one step.
- Credential-free operation for the core analysis tools via the Arctic Shift
  archive: `analyze_post_patterns`, `analyze_acceptance`, `compare_subreddits`,
  `analyze_subreddit`, and `evaluate_draft` all work without Reddit API
  credentials.
- `compare_subreddits`: rank subreddits by opportunity (reach vs. removal risk),
  now also showing typical comment counts as a discussion signal.
- `evaluate_draft`: data-driven 0-100 performance prediction against a sub's own
  score distribution, with per-factor drivers, fixes, and a posting window.
- Configurable `metric` for pattern analysis: `score`, `comments`,
  `discussion` (comments per upvote), and `quality` (clickbait-damped).
- Anti-clickbait intelligence: clickbait detection and a per-sub verdict on
  whether clickbait is rewarded or penalised.
- Command-line interface (`patterns`, `acceptance`, `compare`, `draft`,
  `report`) with `--json` output, `--metric`, and `--tz` for local times.
- Arctic Shift client with pagination, retry/backoff, and per-process caching.

### Accuracy
- Pattern aggregation ranks categories and time buckets by median (outlier
  robust) with minimum-sample gating and per-report confidence levels.
- Stratified sampling for month-and-longer windows, so a high-volume sub's
  sample spans the whole period instead of only the last few days.
- Reported sample date coverage and span, with confidence lowered on thin
  windows.
- Trimmed mean alongside median and mean to temper outlier distortion.
- Posting times ranked by hit-rate (share of posts clearing the 75th
  percentile) rather than an outlier-prone average.
- Removal detection treats AutoMod-filtered posts as uncertain, and flags
  low-confidence samples; an accurate live diff runs when credentials exist.

### Changed
- Response caching, retry/backoff, and local-timezone posting-time display.

### Removed
- The previous project's identity, publishing configs, feed API, Descope auth,
  and vector-search layer.

## [0.1.0]

- Initial pivot to a subreddit and post-pattern analysis engine.
