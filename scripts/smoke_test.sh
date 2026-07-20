#!/usr/bin/env bash
# Smoke-test all 8 reddit-growth tools end to end.
set -uo pipefail
cd "$(dirname "$0")/.."

PY="python -m src.cli"
pass=0; fail=0

run() {
  local desc="$1"; shift
  printf '\n\033[1m### %s\033[0m\n' "$desc"
  if $PY "$@" 2>&1 | sed 's/^/  /'; then
    pass=$((pass+1)); printf '  \033[32m✓ ok\033[0m\n'
  else
    fail=$((fail+1)); printf '  \033[31m✗ FAILED\033[0m\n'
  fi
}

TITLE="I built an MCP server that analyzes subreddit growth"

run "traffic"    traffic LocalLLaMA
run "patterns"   patterns Fedora --time month
run "acceptance" acceptance mcp
run "insight"    insight mcp
run "compare"    compare singularity LocalLLaMA mcp
run "plan"       plan singularity LocalLLaMA --tz 7
run "draft"      draft ClaudeAI --title "$TITLE" --type image
run "fit"        fit singularity mcp --title "$TITLE" --type video

printf '\n\033[1m========================================\033[0m\n'
printf '  \033[32m%d passed\033[0m · \033[31m%d failed\033[0m (of 8 tools)\n' "$pass" "$fail"
printf '\033[1m========================================\033[0m\n\n'
printf 'Press Enter to close…'; read -r _
