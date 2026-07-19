"""Reddit data-access tools — raw fetch/search over posts and comments."""

from .search import search_in_subreddit
from .posts import fetch_subreddit_posts, fetch_multiple_subreddits
from .comments import fetch_submission_with_comments

__all__ = [
    "search_in_subreddit",
    "fetch_subreddit_posts",
    "fetch_multiple_subreddits",
    "fetch_submission_with_comments",
]
