#!/usr/bin/env bash
# Clean, screenshot-friendly demo of the flagship `plan` + `compare` output.
set -uo pipefail
cd "$(dirname "$0")/.."

PY="python -m src.cli"

# Show the command like a real shell session, then run it.
demo() {
  printf '\n\033[38;5;245m$ \033[0m\033[1mreddit-growth %s\033[0m\n\n' "$*"
  $PY "$@"
}

clear
printf '\033[1m════════════════════════════════════════════════════════\033[0m\n'
printf '  \033[1mreddit-growth-mcp  ·  %s\033[0m\n' "$(date '+%Y-%m-%d')"
printf '\033[1m════════════════════════════════════════════════════════\033[0m\n'
demo compare singularity LocalLLaMA mcp
demo plan singularity LocalLLaMA --tz 7

printf '\n\033[38;5;245m# screenshot this window for the README / Reddit post\033[0m\n\n'
read -r _
