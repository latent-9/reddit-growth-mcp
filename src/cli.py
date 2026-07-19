"""Command-line interface for Reddit Analyzer.

Run analyses straight from the terminal — no MCP client needed. Most commands
work without Reddit credentials (data comes from the Arctic archive); when
credentials are present, acceptance/draft also load official rules.

Examples:
    uv run python -m src.cli patterns Fedora --time month
    uv run python -m src.cli acceptance technology
    uv run python -m src.cli compare Fedora gnome linux
    uv run python -m src.cli draft ClaudeAI --title "I built an ASCII art tool"
"""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

from src.analysis.patterns import analyze_post_patterns
from src.analysis.acceptance import analyze_acceptance
from src.analysis.compare import compare_subreddits
from src.analysis.draft import evaluate_draft

load_dotenv()


def _get_reddit():
    """Return a Reddit client if credentials work, else None (archive mode)."""
    try:
        from src.config import get_reddit_client
        return get_reddit_client()
    except Exception:
        return None


def _hr(title: str) -> None:
    print(f"\n\033[1m{title}\033[0m")
    print("─" * min(len(title), 60))


def _print_patterns(d: dict) -> None:
    if "error" in d:
        print("Error:", d["error"]); return
    _hr(f"POST PATTERNS · r/{d['subreddit']}  ({d['source']}, n={d['sampled']})")
    st = d["score_stats"]
    print(f"Score: avg {st['avg']} · median {st['median']} · max {st['max']}")

    _hr("Best media types (avg score)")
    for m in d["score_by_media_type"]:
        print(f"  {str(m['value']):16} {m['avg_score']:>8}   ({m['count']} posts)")

    _hr("Best posting hours (UTC)")
    for h in d["best_posting_hours_utc"][:5]:
        print(f"  {h['hour_utc']:02d}:00   avg {h['avg_score']:>7}   ({h['posts']} posts)")

    _hr("Best days")
    for x in d["best_posting_days"][:3]:
        print(f"  {x['day']:10} avg {x['avg_score']}")

    _hr("Top flairs (avg score)")
    for f in d["score_by_flair"][:6]:
        if f["value"]:
            print(f"  {str(f['value']):20} {f['avg_score']:>8}")

    kw = d.get("winning_keywords", [])
    if kw:
        _hr("Winning keywords (over-represented in top posts)")
        for k in kw[:10]:
            print(f"  {k['word']:18} lift ×{k['lift']:<5} ({k['count_in_top']} top posts)")

    _hr("Title signals (score lift)")
    for name, sig in d["title_signal_lift"].items():
        print(f"  {name:18} {sig['lift_pct']:+.0f}%   (n={sig['sample_with']})")

    _hr("Top examples")
    for ex in d["top_examples"][:5]:
        print(f"  ↑{ex['score']:<6} [{ex['media_type']}] {ex['title'][:70]}")


def _print_acceptance(d: dict) -> None:
    if "error" in d:
        print("Error:", d["error"]); return
    _hr(f"ACCEPTANCE · r/{d['subreddit']}  ({d['detection_method']})")
    print(f"Strictness: {d['strictness']} · removal rate {d['removal_rate_estimate']:.0%} "
          f"({d['mod_removed_count']}/{d['sampled_posts']} removed)")
    print(f"Rules loaded: {d['rules_available']}")

    if d.get("surviving_media_mix"):
        _hr("Surviving posts by media")
        for k, v in sorted(d["surviving_media_mix"].items(), key=lambda x: -x[1]):
            print(f"  {k:14} {v}")

    if d.get("account_gates"):
        _hr("Account gates detected")
        for g in d["account_gates"]:
            print(f"  [{g['type']}] {g['raw']}")

    _hr("Acceptance checklist")
    for c in d.get("acceptance_checklist", []):
        print(f"  • {c}")


def _print_compare(d: dict) -> None:
    if "error" in d:
        print("Error:", d["error"]); return
    _hr("SUBREDDIT COMPARISON  (higher opportunity = better)")
    print(f"{'subreddit':20} {'opp':>7} {'median':>7} {'removal':>8} {'best media':>12}")
    for p in d["ranked"]:
        print(f"  r/{p['subreddit']:17} {p['opportunity_score']:>7} {p['median_score']:>7} "
              f"{p['removal_rate']:>7.0%} {str(p['best_media']):>12}")
    for f in d.get("failed", []):
        print(f"  r/{f['subreddit']:17} — {f['error']}")
    if d.get("best_pick"):
        print(f"\nBest pick: r/{d['best_pick']}")
    print(f"({d['criteria']})")


def _print_draft(d: dict) -> None:
    if "error" in d:
        print("Error:", d["error"]); return
    _hr(f"DRAFT EVALUATION · r/{d['subreddit']}")
    print(f"Verdict: {d['acceptance_verdict']}  ·  engagement score {d['engagement_score']}/100")
    if d.get("blocking_issues"):
        _hr("Blocking issues")
        for i in d["blocking_issues"]:
            print(f"  ✗ {i}")
    if d.get("warnings"):
        _hr("Warnings")
        for w in d["warnings"]:
            print(f"  ! {w}")
    if d.get("engagement_notes"):
        _hr("Engagement notes")
        for n in d["engagement_notes"]:
            print(f"  • {n}")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="reddit-analyzer", description="Analyze subreddits and post patterns.")
    p.add_argument("--json", action="store_true", help="Emit raw JSON instead of a formatted report")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("patterns", help="What makes posts perform in a subreddit")
    sp.add_argument("subreddit")
    sp.add_argument("--time", default="month", choices=["day", "week", "month", "year", "all"])
    sp.add_argument("--limit", type=int, default=200)

    sa = sub.add_parser("acceptance", help="Removal rate + what gets nuked")
    sa.add_argument("subreddit")
    sa.add_argument("--sample", type=int, default=200)

    sc = sub.add_parser("compare", help="Rank subreddits by posting opportunity")
    sc.add_argument("subreddits", nargs="+")
    sc.add_argument("--window", default="60d")
    sc.add_argument("--sample", type=int, default=200)

    sd = sub.add_parser("draft", help="Evaluate a post draft")
    sd.add_argument("subreddit")
    sd.add_argument("--title", required=True)
    sd.add_argument("--body", default="")
    sd.add_argument("--type", default="text", dest="post_type")
    sd.add_argument("--flair", default=None)

    args = p.parse_args(argv)
    reddit = _get_reddit()
    if reddit is None and args.cmd in {"patterns", "acceptance", "compare", "draft"}:
        print("(no Reddit credentials — using archive mode)", file=sys.stderr)

    if args.cmd == "patterns":
        result = analyze_post_patterns(args.subreddit, reddit, "top", args.time, args.limit, "auto")
        printer = _print_patterns
    elif args.cmd == "acceptance":
        result = analyze_acceptance(args.subreddit, reddit, args.sample)
        printer = _print_acceptance
    elif args.cmd == "compare":
        result = compare_subreddits(args.subreddits, args.window, args.sample)
        printer = _print_compare
    elif args.cmd == "draft":
        result = evaluate_draft(args.subreddit, args.title, reddit, args.body, args.post_type, args.flair)
        printer = _print_draft
    else:  # pragma: no cover
        p.error("unknown command")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        printer(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
