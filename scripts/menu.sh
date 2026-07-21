#!/usr/bin/env bash
# Interactive launcher — pick a mode, choose subreddits, see the result.
# Uses `gum` for a modern TUI when available; falls back to a numbered menu.
set -uo pipefail
cd "$(dirname "$0")/.."

PY="python -m src.cli"
TZ_OFFSET="${RG_TZ:-7}"   # local-time offset for plan/draft (override with RG_TZ)
HAS_GUM=0; command -v gum >/dev/null 2>&1 && HAS_GUM=1

# Theme gum: orange accent (was pink 212), readable text (was faint 240).
if [ "$HAS_GUM" = 1 ]; then
  export GUM_CHOOSE_CURSOR_FOREGROUND=208 GUM_CHOOSE_SELECTED_FOREGROUND=208 GUM_CHOOSE_HEADER_FOREGROUND=208
  export GUM_FILTER_INDICATOR_FOREGROUND=208 GUM_FILTER_SELECTED_PREFIX_FOREGROUND=208
  export GUM_FILTER_MATCH_FOREGROUND=220 GUM_FILTER_HEADER_FOREGROUND=208
  export GUM_FILTER_PROMPT_FOREGROUND=208 GUM_FILTER_PLACEHOLDER_FOREGROUND=245
  export GUM_INPUT_CURSOR_FOREGROUND=208 GUM_INPUT_PROMPT_FOREGROUND=208 GUM_INPUT_HEADER_FOREGROUND=208
  # Hide gum's low-contrast help footer; we show readable hints in the header.
  export GUM_FILTER_SHOW_HELP=false GUM_CHOOSE_SHOW_HELP=false
fi

T='\033[1m'; D='\033[38;5;245m'; G='\033[38;5;40m'; Y='\033[38;5;220m'
C='\033[38;5;44m'; O='\033[38;5;208m'; R='\033[0m'
GO=208; GC=42; GD=245; GY=220   # gum color codes

cls()  { command clear 2>/dev/null || printf '\033[H\033[2J'; }
line() { printf "${D}────────────────────────────────────────────────────────${R}\n"; }
banner(){ printf "\n${G}${T}▶ %s${R}\n\n" "$1"; }
run()  { printf "\n${D}\$ ${R}${T}reddit-growth %s${R}\n${D}   …fetching from the archive (a few seconds)…${R}\n\n" "$*"; $PY "$@"; }
pause(){ printf "\n${D}──  press enter to return to the menu  ──${R}"; read -r _; }

# All verified to have archive data.
SUBS_OPTS=(ChatGPT OpenAI ClaudeAI grok DeepSeek Bard perplexity_ai MistralAI \
           LocalLLaMA ollama mcp cursor LLMDevs PromptEngineering \
           singularity artificial Futurology aiwars MachineLearning \
           StableDiffusion midjourney comfyui dataisbeautiful \
           programming Python javascript rust webdev coolgithubprojects \
           selfhosted homelab buildapc technology \
           SaaS SideProject startups indiehackers Entrepreneur marketing SEO growthhacking)

logo_ansi() {
  printf "\n"
  printf "   ${O}${T}reddit${R}${D}·${R}${G}${T}growth${R}   ${G}▁▂▃▄▅▇${R}${O}↗${R}\n"
  printf "   ${D}────────────────────────────────────${R}\n"
  printf "   ${D}Ready to grow? Pick a mode and find where you'll be seen ${R}${G}↓${R}\n"
}

show_header() {
  cls
  if [ "$HAS_GUM" = 1 ]; then
    gum style --border rounded --border-foreground "$GO" --foreground "$GO" --bold \
      --padding "0 3" --margin "1 0 0 1" "reddit·growth   ▁▂▃▄▅▇↗"
    gum style --foreground 250 --margin "0 0 1 2" \
      "Ready to grow? Pick a mode — find where you'll be seen ↓"
  else
    logo_ansi; line
  fi
}

# ---- selection helpers (gum when available, numbered fallback otherwise) ----
MODES=(
  "plan|where to post + tags + content + when"
  "compare|rank subs by growth / viral / safety"
  "patterns|deep analysis: the viral recipe"
  "draft|score ONE post before you submit"
  "fit|score one draft across several subs"
  "traffic|activity (posts/day)"
  "insight|discussion depth + sentiment"
  "acceptance|removal rate + what gets removed"
  "report|acceptance + patterns together"
  "help|what to type"
  "quit|"
)

choose_mode() {
  if [ "$HAS_GUM" = 1 ]; then
    local opts=() m
    for m in "${MODES[@]}"; do opts+=("$(printf '%-11s %s' "${m%%|*}" "${m#*|}")"); done
    local sel
    sel=$(printf '%s\n' "${opts[@]}" | gum choose --height 13 \
      --header "  what do you want to do?   ↑↓ move · enter select" --cursor "❯ ") || { choice=quit; return; }
    choice=$(printf '%s' "$sel" | awk '{print $1}')
  else
    numbered_menu; read -r choice
  fi
}

# gum filter = fuzzy-searchable list. --no-limit for multi-select.
choose_subs() {
  if [ "$HAS_GUM" = 1 ]; then
    SUBS=$(printf '%s\n' "${SUBS_OPTS[@]}" | gum filter --no-limit --height 15 \
      --placeholder "type to filter…" \
      --header "  pick subreddit(s)   type to search · tab select · enter confirm" \
      --indicator "▸" | tr '\n' ' ')
  else
    pick; SUBS="$SEL"
  fi
}
choose_one() {
  if [ "$HAS_GUM" = 1 ]; then
    SUB=$(printf '%s\n' "${SUBS_OPTS[@]}" | gum filter --height 15 \
      --placeholder "type to filter…" --header "  pick a subreddit   type to search · enter select")
  else
    pick; SUB="${SEL%% *}"
  fi
}
ask_title() {
  if [ "$HAS_GUM" = 1 ]; then
    TITLE=$(gum input --width 90 --header "  post title" \
      --placeholder "I mapped 10 years of GPU prices [OC]")
    TYPE=$(gum choose --header "  post type" image text video link)
  else
    printf "${Y}  post title${R} ${D}— e.g.  I mapped 10 years of GPU prices [OC]${R}\n${Y}  ▸ ${R}"; read -r TITLE
    printf "${Y}  post type${R} ${D}— text / image / video / link (default image)${R}\n${Y}  ▸ ${R}"; read -r TYPE; TYPE="${TYPE:-image}"
  fi
  TYPE="${TYPE:-image}"
}

# ---- numbered fallback (no gum) ----
pick() {
  printf "${D}  pick number(s) — e.g.  ${R}1 4 5${D}  — or just type subreddit name(s):${R}\n\n"
  printf "  ${C}AI chat${R}     ${G}1${R} ChatGPT  ${G}2${R} OpenAI  ${G}3${R} ClaudeAI  ${G}4${R} grok  ${G}5${R} DeepSeek  ${G}6${R} Bard  ${G}7${R} perplexity_ai  ${G}8${R} MistralAI\n"
  printf "  ${C}agents/AI${R}   ${G}9${R} LocalLLaMA  ${G}10${R} ollama  ${G}11${R} mcp  ${G}12${R} cursor  ${G}13${R} LLMDevs  ${G}14${R} PromptEngineering\n"
  printf "  ${C}AI general${R}  ${G}15${R} singularity  ${G}16${R} artificial  ${G}17${R} Futurology  ${G}18${R} aiwars  ${G}19${R} MachineLearning\n"
  printf "  ${C}image/data${R}  ${G}20${R} StableDiffusion  ${G}21${R} midjourney  ${G}22${R} comfyui  ${G}23${R} dataisbeautiful\n"
  printf "  ${C}dev${R}         ${G}24${R} programming  ${G}25${R} Python  ${G}26${R} javascript  ${G}27${R} rust  ${G}28${R} webdev  ${G}29${R} coolgithubprojects\n"
  printf "  ${C}infra/hw${R}    ${G}30${R} selfhosted  ${G}31${R} homelab  ${G}32${R} buildapc  ${G}33${R} technology\n"
  printf "  ${C}startup/biz${R} ${G}34${R} SaaS  ${G}35${R} SideProject  ${G}36${R} startups  ${G}37${R} indiehackers  ${G}38${R} Entrepreneur  ${G}39${R} marketing  ${G}40${R} SEO  ${G}41${R} growthhacking\n\n"
  printf "${Y}  ▸ ${R}"; read -r raw
  SEL=""
  for tok in $raw; do
    if [[ "$tok" =~ ^[0-9]+$ ]] && [ "$tok" -ge 1 ] && [ "$tok" -le "${#SUBS_OPTS[@]}" ]; then
      SEL="$SEL ${SUBS_OPTS[$((tok - 1))]}"
    else
      SEL="$SEL $tok"
    fi
  done
  SEL="${SEL# }"
}

numbered_menu() {
  cls; logo_ansi; line
  printf "  ${G}1${R}  ${T}plan${R}        ${D}where to post + tags + content + when${R}\n"
  printf "  ${G}2${R}  ${T}compare${R}     ${D}rank subs by growth / viral / safety${R}\n"
  printf "  ${G}3${R}  ${T}patterns${R}    ${D}deep analysis: the viral recipe${R}\n"
  printf "  ${G}4${R}  ${T}draft${R}       ${D}score ONE post before you submit${R}\n"
  printf "  ${G}5${R}  ${T}fit${R}         ${D}score one draft across several subs${R}\n"
  printf "  ${G}6${R}  ${T}traffic${R}     ${D}activity (posts/day)${R}\n"
  printf "  ${G}7${R}  ${T}insight${R}     ${D}discussion depth + sentiment${R}\n"
  printf "  ${G}8${R}  ${T}acceptance${R}  ${D}removal rate + what gets removed${R}\n"
  printf "  ${G}9${R}  ${T}report${R}      ${D}acceptance + patterns together${R}\n"
  line
  printf "  ${G}h${R}  ${D}help — what to type${R}      ${G}q${R}  ${D}quit${R}\n\n"
  printf "  ${T}choose ▸ ${R}"
}

help_screen() {
  cls; logo_ansi; line
  printf "  ${T}HOW TO USE${R} ${D}— pick a mode, then choose subreddits (type to filter${R}\n"
  printf "  ${D}with gum, or by number). No Reddit account needed.${R}\n\n"
  printf "  ${T}“Where should I post to grow my account?”${R}  ${G}plan${R} ${D}·${R} ${G}compare${R}\n"
  printf "  ${T}“What kind of post works in a sub?”${R}        ${G}patterns${R}\n"
  printf "  ${T}“Will MY post do well / get removed?”${R}       ${G}draft${R} ${D}·${R} ${G}fit${R}\n"
  printf "  ${T}“How active / strict / deep is a sub?”${R}      ${G}traffic${R} ${D}·${R} ${G}acceptance${R} ${D}·${R} ${G}insight${R} ${D}·${R} ${G}report${R}\n\n"
  line
  printf "  ${D}tip: exact sub name (no r/) · pick several for plan/compare/fit${R}\n"
  pause
}

while true; do
  show_header
  choose_mode
  case "$choice" in
    1|plan)       banner "plan — where to post · tags · content · timing"; choose_subs; [ -n "${SUBS:-}" ] && { run plan $SUBS --tz "$TZ_OFFSET"; pause; } ;;
    2|compare)    banner "compare — rank subreddits by growth potential"; choose_subs; [ -n "${SUBS:-}" ] && { run compare $SUBS; pause; } ;;
    3|patterns)   banner "patterns — the viral recipe for one sub"; choose_one; [ -n "${SUB:-}" ] && { run patterns "$SUB" --time month; pause; } ;;
    4|draft)      banner "draft — score one post before you submit"; choose_one; [ -n "${SUB:-}" ] && { ask_title; run draft "$SUB" --title "$TITLE" --type "$TYPE"; pause; } ;;
    5|fit)        banner "fit — score one draft across several subs"; choose_subs; [ -n "${SUBS:-}" ] && { ask_title; run fit $SUBS --title "$TITLE" --type "$TYPE"; pause; } ;;
    6|traffic)    banner "traffic — how active is a sub"; choose_one; [ -n "${SUB:-}" ] && { run traffic "$SUB"; pause; } ;;
    7|insight)    banner "insight — discussion depth + sentiment"; choose_one; [ -n "${SUB:-}" ] && { run insight "$SUB"; pause; } ;;
    8|acceptance) banner "acceptance — removal rate + what gets removed"; choose_one; [ -n "${SUB:-}" ] && { run acceptance "$SUB"; pause; } ;;
    9|report)     banner "report — acceptance + patterns together"; choose_one; [ -n "${SUB:-}" ] && { run report "$SUB"; pause; } ;;
    h|H|help)     help_screen ;;
    q|Q|quit)     cls; printf "  ${D}bye 👋${R}\n"; exit 0 ;;
    "") ;;
    *) printf "\n  ${Y}“%s” isn't a mode — pick from the list, or h for help.${R}" "$choice"; sleep 1.2 ;;
  esac
done
