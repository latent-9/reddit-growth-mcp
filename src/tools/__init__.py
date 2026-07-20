"""Reddit data-access tools — raw fetch/search over posts and comments."""

from .comments import fetch_submission_with_comments
from .posts import fetch_multiple_subreddits, fetch_subreddit_posts
from .search import search_in_subreddit

__all__ = [
    "search_in_subreddit",
    "fetch_subreddit_posts",
    "fetch_multiple_subreddits",
    "fetch_submission_with_comments",
]
