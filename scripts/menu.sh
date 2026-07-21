#!/usr/bin/env bash
# Interactive launcher — pick a mode, type the subreddits, see the result.
# One window, menu-driven; loops until you quit.
set -uo pipefail
cd "$(dirname "$0")/.."

PY="python -m src.cli"
TZ_OFFSET="${RG_TZ:-7}"   # local-time offset for plan/draft (override with RG_TZ)

T='\033[1m'; D='\033[38;5;245m'; G='\033[38;5;40m'; Y='\033[38;5;220m'
C='\033[38;5;44m'; O='\033[38;5;208m'; R='\033[0m'

cls()  { command clear 2>/dev/null || printf '\033[H\033[2J'; }
line() { printf "${D}────────────────────────────────────────────────────────${R}\n"; }
banner(){ printf "\n${G}${T}▶ %s${R}\n\n" "$1"; }
run()  { printf "\n${D}\$ ${R}${T}reddit-growth %s${R}\n${D}   …fetching from the archive (a few seconds)…${R}\n\n" "$*"; $PY "$@"; }
pause(){ printf "\n${D}──  press enter to return to the menu  ──${R}"; read -r _; }

logo() {
  printf "\n"
  printf "   ${O}${T}reddit${R}${D}·${R}${G}${T}growth${R}   ${G}▁▂▃▄▅▇${R}${O}↗${R}\n"
  printf "   ${D}────────────────────────────────────${R}\n"
  printf "   ${D}find the sub that grows you — and what to post${R}\n"
}

# Preset subreddits (all verified to have archive data). Numbered for quick pick.
SUBS_OPTS=(ChatGPT OpenAI ClaudeAI grok DeepSeek Bard perplexity_ai MistralAI \
           LocalLLaMA ollama mcp cursor LLMDevs \
           singularity artificial Futurology aiwars MachineLearning \
           StableDiffusion midjourney comfyui dataisbeautiful \
           programming Python javascript rust webdev \
           selfhosted homelab buildapc technology)

# Show the pick-list, read numbers (or typed names), resolve into SEL.
pick() {
  printf "${D}  pick number(s) — e.g.  ${R}1 4 5${D}  — or just type subreddit name(s):${R}\n\n"
  printf "  ${C}AI chat${R}    ${G}1${R} ChatGPT  ${G}2${R} OpenAI  ${G}3${R} ClaudeAI  ${G}4${R} grok  ${G}5${R} DeepSeek  ${G}6${R} Bard  ${G}7${R} perplexity_ai  ${G}8${R} MistralAI\n"
  printf "  ${C}agents/local${R} ${G}9${R} LocalLLaMA  ${G}10${R} ollama  ${G}11${R} mcp  ${G}12${R} cursor  ${G}13${R} LLMDevs\n"
  printf "  ${C}AI general${R} ${G}14${R} singularity  ${G}15${R} artificial  ${G}16${R} Futurology  ${G}17${R} aiwars  ${G}18${R} MachineLearning\n"
  printf "  ${C}image/data${R} ${G}19${R} StableDiffusion  ${G}20${R} midjourney  ${G}21${R} comfyui  ${G}22${R} dataisbeautiful\n"
  printf "  ${C}dev${R}        ${G}23${R} programming  ${G}24${R} Python  ${G}25${R} javascript  ${G}26${R} rust  ${G}27${R} webdev\n"
  printf "  ${C}infra/hw${R}   ${G}28${R} selfhosted  ${G}29${R} homelab  ${G}30${R} buildapc  ${G}31${R} technology\n\n"
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

askS() { pick; SUBS="$SEL"; }
ask1() { pick; SUB="${SEL%% *}"; }   # single-sub modes take the first pick
askT() {
  printf "${Y}  post title${R} ${D}— e.g.  I mapped 10 years of GPU prices [OC]${R}\n${Y}  ▸ ${R}"; read -r TITLE
  printf "${Y}  post type${R} ${D}— text / image / video / link  (default: image)${R}\n${Y}  ▸ ${R}"; read -r TYPE; TYPE="${TYPE:-image}"
}

help_screen() {
  cls
  logo
  line
  printf "  ${T}HOW TO USE${R} ${D}— after picking a mode, choose subreddits by number${R}\n"
  printf "  ${D}from the list (e.g. “1 10”) or type names. No Reddit account needed.${R}\n\n"

  printf "  ${T}“Where should I post to grow my account?”${R}\n"
  printf "    ${G}1 plan${R}     ${D}type:${R} StableDiffusion dataisbeautiful comfyui\n"
  printf "    ${G}2 compare${R}  ${D}type:${R} StableDiffusion dataisbeautiful\n\n"

  printf "  ${T}“What kind of post works in a sub?”${R}\n"
  printf "    ${G}3 patterns${R} ${D}type:${R} dataisbeautiful\n\n"

  printf "  ${T}“Will MY post do well / get removed?”${R}\n"
  printf "    ${G}4 draft${R}    ${D}type:${R} dataisbeautiful  ${D}then a title + post type${R}\n"
  printf "    ${G}5 fit${R}      ${D}type:${R} several subs  ${D}then a title (finds best-fit sub)${R}\n\n"

  printf "  ${T}“How active / strict / deep is a sub?”${R}\n"
  printf "    ${G}6 traffic${R}    ${D}·${R} ${G}8 acceptance${R} ${D}·${R} ${G}7 insight${R} ${D}·${R} ${G}9 report${R}  ${D}type:${R} dataisbeautiful\n\n"

  line
  printf "  ${D}tips:  exact sub name (no r/)  ·  multiple = separate with spaces${R}\n"
  printf "  ${D}       no data? that sub isn't archived — try a bigger/related one${R}\n"
  pause
}

menu() {
  cls
  logo
  line
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

while true; do
  menu
  read -r choice
  case "$choice" in
    1) banner "plan — where to post · tags · content · timing"; askS; [ -n "${SUBS:-}" ] && { run plan $SUBS --tz "$TZ_OFFSET"; pause; } ;;
    2) banner "compare — rank subreddits by growth potential"; askS; [ -n "${SUBS:-}" ] && { run compare $SUBS; pause; } ;;
    3) banner "patterns — the viral recipe for one sub"; ask1; [ -n "${SUB:-}" ] && { run patterns "$SUB" --time month; pause; } ;;
    4) banner "draft — score one post before you submit"; ask1; [ -n "${SUB:-}" ] && { askT; run draft "$SUB" --title "$TITLE" --type "$TYPE"; pause; } ;;
    5) banner "fit — score one draft across several subs"; askS; [ -n "${SUBS:-}" ] && { askT; run fit $SUBS --title "$TITLE" --type "$TYPE"; pause; } ;;
    6) banner "traffic — how active is a sub"; ask1; [ -n "${SUB:-}" ] && { run traffic "$SUB"; pause; } ;;
    7) banner "insight — discussion depth + sentiment"; ask1; [ -n "${SUB:-}" ] && { run insight "$SUB"; pause; } ;;
    8) banner "acceptance — removal rate + what gets removed"; ask1; [ -n "${SUB:-}" ] && { run acceptance "$SUB"; pause; } ;;
    9) banner "report — acceptance + patterns together"; ask1; [ -n "${SUB:-}" ] && { run report "$SUB"; pause; } ;;
    h|H|help|\?) help_screen ;;
    q|Q) cls; printf "  ${D}bye 👋${R}\n"; exit 0 ;;
    "") ;;
    *) printf "\n  ${Y}“%s” isn't a mode — pick 1-9, h for help, or q.${R}" "$choice"; sleep 1.3 ;;
  esac
done
