#!/usr/bin/env bash
# "Will this post boom?" — score a real draft across subs, then deep-dive the
# winner. Focus is post success (reach / viral), not any single subreddit.
set -uo pipefail
cd "$(dirname "$0")/.."

PY="python -m src.cli"
SUBS=(singularity OpenAI ChatGPT mcp)
TITLE="I analyzed 200 posts to find what actually goes viral on Reddit"
TODAY="$(date '+%Y-%m-%d')"

demo() {
  printf '\n\033[38;5;245m$ \033[0m\033[1mreddit-growth %s\033[0m\n\n' "$*"
  $PY "$@"
}

clear
printf '\033[1m════════════════════════════════════════════════════════\033[0m\n'
printf '  \033[1mWill this post boom?  ·  %s\033[0m\n' "$TODAY"
printf '  draft: "%s"\n' "$TITLE"
printf '\033[1m════════════════════════════════════════════════════════\033[0m\n'

# 1. Which community would this post boom in? (ranked by fit + reach)
demo fit "${SUBS[@]}" --title "$TITLE" --type image

# 2. Full scorecard for the top pick — projected reach, drivers, what to tweak.
demo draft singularity --title "$TITLE" --type image

printf '\n\033[38;5;245m# boom check done — screenshot this window\033[0m\n\n'
read -r _
