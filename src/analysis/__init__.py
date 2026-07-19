"""Reddit analysis engine.

Modules:
- helpers:    shared feature extraction (title, media, timing, removal).
- traffic:    subreddit traffic estimation and target discovery.
- acceptance: rules + empirical removal analysis ("will my post be accepted?").
- patterns:   viral / high-engagement post patterns.
- draft:      combine acceptance + patterns to evaluate a post draft.
"""
