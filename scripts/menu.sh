#!/usr/bin/env bash
# Interactive launcher — pick a mode, type the subreddits, see the result.
# One window, menu-driven; loops until you quit.
set -uo pipefail
cd "$(dirname "$0")/.."

PY="python -m src.cli"
TZ_OFFSET="${RG_TZ:-7}"   # local-time offset for plan/draft (override with RG_TZ)

T='\033[1m'; D='\033[38;5;245m'; G='\033[38;5;40m'; Y='\033[38;5;220m'; R='\033[0m'

cls()  { command clear 2>/dev/null || printf '\033[H\033[2J'; }
hr()   { printf "${T}════════════════════════════════════════════════════════${R}\n"; }
run()  { printf "\n${D}\$ ${R}${T}reddit-growth %s${R}\n\n" "$*"; printf "${D}…fetching (archive)…${R}\r"; $PY "$@"; }
pause(){ printf "\n${D}— press enter to return to the menu —${R}"; read -r _; }
askS() { read -rp "$(printf "${Y}  subreddit(s), space-separated: ${R}")" SUBS; }
ask1() { read -rp "$(printf "${Y}  subreddit: ${R}")" SUB; }
askT() { read -rp "$(printf "${Y}  title: ${R}")" TITLE; read -rp "$(printf "${Y}  type [image]: ${R}")" TYPE; TYPE="${TYPE:-image}"; }

menu() {
  cls
  hr
  printf "  ${T}reddit-growth — pick a mode${R}   ${D}(tz +%s)${R}\n" "$TZ_OFFSET"
  hr
  printf "  ${G}1${R}) plan        where to post + tags + content + when\n"
  printf "  ${G}2${R}) compare     rank subs by growth / viral / safety\n"
  printf "  ${G}3${R}) patterns    deep analysis: the viral recipe\n"
  printf "  ${G}4${R}) draft       score ONE post before you submit\n"
  printf "  ${G}5${R}) fit         score one draft across several subs\n"
  printf "  ${G}6${R}) traffic     activity (posts/day)\n"
  printf "  ${G}7${R}) insight     discussion depth + sentiment\n"
  printf "  ${G}8${R}) acceptance  removal rate + what gets removed\n"
  printf "  ${G}9${R}) report      acceptance + patterns together\n"
  printf "  ${G}q${R}) quit\n\n"
  printf "  ${T}choose > ${R}"
}

while true; do
  menu
  read -r choice
  case "$choice" in
    1) askS; [ -n "${SUBS:-}" ] && { run plan $SUBS --tz "$TZ_OFFSET"; pause; } ;;
    2) askS; [ -n "${SUBS:-}" ] && { run compare $SUBS; pause; } ;;
    3) ask1; [ -n "${SUB:-}" ] && { run patterns "$SUB" --time month; pause; } ;;
    4) ask1; [ -n "${SUB:-}" ] && { askT; run draft "$SUB" --title "$TITLE" --type "$TYPE"; pause; } ;;
    5) askS; [ -n "${SUBS:-}" ] && { askT; run fit $SUBS --title "$TITLE" --type "$TYPE"; pause; } ;;
    6) ask1; [ -n "${SUB:-}" ] && { run traffic "$SUB"; pause; } ;;
    7) ask1; [ -n "${SUB:-}" ] && { run insight "$SUB"; pause; } ;;
    8) ask1; [ -n "${SUB:-}" ] && { run acceptance "$SUB"; pause; } ;;
    9) ask1; [ -n "${SUB:-}" ] && { run report "$SUB"; pause; } ;;
    q|Q) cls; printf "bye 👋\n"; exit 0 ;;
    *) ;;
  esac
done
