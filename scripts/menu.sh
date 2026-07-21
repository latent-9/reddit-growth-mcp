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
  printf "${O}        .-.${R}\n"
  printf "${O}       (o.o)${R}    ${C}${T}reddit-growth${R}\n"
  printf "${O}     ___${T}|=|${R}${O}___${R}  ${D}grow where you'll be seen${R}\n"
  printf "${O}    /  '-'  \\\\${R}\n"
}

# Prompts show an example, then a clear "> " input line.
askS() { printf "${Y}  subreddit(s)${R} ${D}— space-separated, e.g.  StableDiffusion dataisbeautiful${R}\n${Y}  ▸ ${R}"; read -r SUBS; }
ask1() { printf "${Y}  subreddit${R} ${D}— e.g.  dataisbeautiful${R}\n${Y}  ▸ ${R}"; read -r SUB; }
askT() {
  printf "${Y}  post title${R} ${D}— e.g.  I mapped 10 years of GPU prices [OC]${R}\n${Y}  ▸ ${R}"; read -r TITLE
  printf "${Y}  post type${R} ${D}— text / image / video / link  (default: image)${R}\n${Y}  ▸ ${R}"; read -r TYPE; TYPE="${TYPE:-image}"
}

help_screen() {
  cls
  logo
  line
  printf "  ${T}HOW TO USE${R} ${D}— give it subreddit names (no “r/”). Most modes need${R}\n"
  printf "  ${D}no Reddit account; data comes from the public archive.${R}\n\n"

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
