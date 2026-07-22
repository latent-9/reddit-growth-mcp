#!/usr/bin/env bash
# All flagship commands in one screenshot-friendly window.
# For one-command-per-window shots (easier to caption), run scripts/win/*.sh.
# shellcheck source=scripts/lib.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

clear
printf '\033[1m════════════════════════════════════════════════════════\033[0m\n'
printf '  \033[38;5;208m\033[1mreddit-growth-mcp\033[0m  ·  %s\n' "$(date '+%Y-%m-%d')"
printf '\033[1m════════════════════════════════════════════════════════\033[0m\n'

show compare singularity LocalLLaMA ChatGPT mcp
show plan singularity LocalLLaMA ChatGPT
show draft LocalLLaMA \
  --title "I built a local RAG that runs fully offline on a laptop" --type image
show patterns LocalLLaMA

hold
