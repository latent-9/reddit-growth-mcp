# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project aims to follow
semantic versioning.

## [Unreleased]

### Added
- Credential-free operation for the core analysis tools via the Arctic Shift
  archive: `analyze_post_patterns`, `analyze_acceptance`, `compare_subreddits`,
  and `evaluate_draft` all work without Reddit API credentials.
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
