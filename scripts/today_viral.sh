#!/usr/bin/env bash
# "What should I post today to go viral?" — where, what theme, and the score.
set -uo pipefail
cd "$(dirname "$0")/.."

PY="python -m src.cli"
SUBS=(singularity OpenAI ChatGPT mcp)
TITLE="I open-sourced an MCP tool that turns 200 Reddit posts into a viral playbook"
TODAY="$(date '+%A · %Y-%m-%d')"

demo() {
  printf '\n\033[38;5;245m$ \033[0m\033[1mreddit-growth %s\033[0m\n\n' "$*"
  $PY "$@"
}

clear
printf '\033[1m════════════════════════════════════════════════════════\033[0m\n'
printf '  \033[1mWhat to post today to go viral?  ·  %s\033[0m\n' "$TODAY"
printf '\033[1m════════════════════════════════════════════════════════\033[0m\n'

# WHERE + THEME + WHEN: best safe target, viral recipe (keywords = hot theme).
demo plan "${SUBS[@]}" --tz 7

# VIRAL POTENTIAL: score a draft that rides the recipe.
demo draft singularity --title "$TITLE" --type image

printf '\n\033[38;5;245m# recommendation ready — screenshot this window\033[0m\n\n'
read -r _
