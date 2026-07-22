#!/usr/bin/env bash
# Shared helpers for the demo / screenshot scripts. Source this, then call
# `one <cmd...>` (single window) or `show`/`hold` (compose your own sequence).
set -uo pipefail

# Repo root, resolved from THIS file's location — depth-independent and free of
# any machine-specific path, so the scripts stay portable across checkouts.
_LIB_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$_LIB_DIR/.." || exit 1

# Put the project's `reddit-growth` on PATH; fall back to the module form.
# shellcheck disable=SC1091
[ -f .venv/bin/activate ] && source .venv/bin/activate
RG="reddit-growth"
command -v "$RG" >/dev/null 2>&1 || RG="python -m src.cli"

# Echo the command like a real shell prompt, then run it verbatim.
show() {
  printf '\n\033[38;5;245m$ \033[0m\033[1mreddit-growth %s\033[0m\n\n' "$*"
  $RG "$@"
}

# Footer that pauses so the window stays open for a screenshot.
hold() {
  printf '\n\033[38;5;208m# screenshot this window\033[0m  (press Enter to close)\n'
  read -r _
}

# One command in its own clean window: clear, run, pause.
one() {
  clear
  show "$@"
  hold
}
