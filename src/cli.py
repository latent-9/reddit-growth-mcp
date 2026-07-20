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

from src.analysis.acceptance import analyze_acceptance
from src.analysis.compare import compare_subreddits
from src.analysis.draft import evaluate_draft, evaluate_draft_across
from src.analysis.insight import analyze_insight
from src.analysis.patterns import analyze_post_patterns
from src.analysis.plan import build_growth_plan
from src.analysis.traffic import estimate_activity_archive

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


def _fmt_hour(hour_utc: int, tz: float) -> str:
    """Render an hour as UTC, plus local time when a tz offset is given."""
    if not tz:
        return f"{hour_utc:02d}:00 UTC"
    local = (hour_utc + tz) % 24
    lh, lm = int(local), int(round((local % 1) * 60))
    return f"{hour_utc:02d}:00 UTC = {lh:02d}:{lm:02d} local"


def _print_patterns(d: dict, tz: float = 0.0) -> None:
    if "error" in d:
        print("Error:", d["error"])
        return
    _hr(
        f"POST PATTERNS · r/{d['subreddit']}  ({d['source']}, metric={d.get('metric')}, "
        f"n={d['sampled']}, confidence={d.get('confidence')})"
    )
    rng = d.get("sample_date_range")
    if rng:
        print(f"Coverage: {rng['oldest']} to {rng['newest']} ({d.get('sample_span_days')} days)")
    st = d["score_stats"]
    print(
        f"{d.get('metric', 'score')}: median {st['median']} · trimmed-mean "
        f"{st.get('trimmed_mean')} · mean {st['mean']} · max {st['max']}"
    )
    print("(ranked by median = typical post; trimmed-mean drops outliers)")
    cb = d.get("clickbait_effect", {})
    if cb:
        print(
            f"Clickbait here: {cb.get('verdict')} "
            f"(baity mean {cb.get('clickbait_avg')} vs clean {cb.get('clean_avg')}, "
            f"{cb.get('lift_pct')}%)"
        )

    _hr("Best media types (median / mean)")
    for m in d["score_by_media_type"]:
        print(f"  {str(m['value']):16} med {m['median']:>7} / mean {m['mean']:>7}   ({m['count']} posts)")

    _hr("Best time blocks (by hit-rate = share of strong posts)")
    for b in d.get("best_time_blocks", []):
        print(f"  {b['block']:12} hit {b.get('hit_rate', 0):>5.0%}   mean {b['mean']:>7}   ({b['posts']} posts)")

    _hr("Best posting hours (>=3 posts, by hit-rate)")
    for h in d["best_posting_hours_utc"][:5]:
        print(
            f"  {_fmt_hour(h['hour_utc'], tz):<28} hit {h.get('hit_rate', 0):>5.0%}   "
            f"mean {h['mean']:>6}   ({h['posts']} posts)"
        )

    _hr("Best days (by hit-rate)")
    for x in d["best_posting_days"][:3]:
        print(f"  {x['day']:10} hit {x.get('hit_rate', 0):>5.0%}   mean {x['mean']}   ({x['posts']} posts)")

    _hr("Top flairs (median / mean)")
    for f in d["score_by_flair"][:6]:
        if f["value"]:
            print(f"  {str(f['value']):20} med {f['median']:>7} / mean {f['mean']:>7}   ({f['count']} posts)")

    kw = d.get("winning_keywords", [])
    if kw:
        _hr("Winning keywords (over-represented in top posts)")
        for k in kw[:10]:
            print(f"  {k['word']:18} lift ×{k['lift']:<5} ({k['count_in_top']} top posts)")

    _hr("Title signals (score lift)")
    for name, sig in d["title_signal_lift"].items():
        print(f"  {name:18} {sig['lift_pct']:+.0f}%   (n={sig['sample_with']})")

    vp = d.get("viral_profile", {})
    if vp.get("available"):
        rc = vp["recipe"]
        _hr(f"VIRAL RECIPE (top {vp['viral_count']} posts, score >= {vp['viral_threshold']})")
        print(f"  Media : {rc['media_type']['value']} ({rc['media_type']['share']:.0%} of viral)")
        if rc["flair"]["value"]:
            print(f"  Flair : {rc['flair']['value']} ({rc['flair']['share']:.0%})")
        tag = rc.get("title_tag", {})
        if tag.get("share", 0) >= 0.3 and tag.get("common"):
            tags = ", ".join(f"[{t}]" for t in tag["common"])
            print(f"  Tag   : prefix title with {tags} ({tag['share']:.0%} of viral do)")
        print(f"  Time  : {rc['time_block_utc']['value']} ({rc['time_block_utc']['share']:.0%})")
        t = rc["title"]
        traits = [
            n
            for n, key in [
                ("question", "question"),
                ("showcase", "showcase"),
                ("numbers", "has_number"),
                ("clickbait", "clickbait"),
            ]
            if t[key]["overrepresented"]
        ]
        print(
            f"  Title : ~{t['median_char_length']} chars"
            + (f"; over-represented: {', '.join(traits)}" if traits else "")
        )
        if rc["keywords"]:
            print(f"  Words : {', '.join(rc['keywords'][:6])}")

    _hr("Top examples")
    for ex in d["top_examples"][:5]:
        cbf = " ⚠cb" if ex.get("clickbait", 0) >= 0.4 else ""
        print(f"  ↑{ex['score']:<6} 💬{ex.get('num_comments', 0):<5}{cbf} [{ex['media_type']}] {ex['title'][:60]}")


def _print_acceptance(d: dict) -> None:
    if "error" in d:
        print("Error:", d["error"])
        return
    _hr(f"ACCEPTANCE · r/{d['subreddit']}  ({d['detection_method']}, reliability: {d.get('reliability')})")
    print(
        f"Strictness: {d['strictness']} · confirmed removal rate {d['removal_rate_estimate']:.0%} "
        f"({d['mod_removed_count']}/{d['sampled_posts']} confirmed)"
    )
    if d.get("automod_filtered_count"):
        print(f"AutoMod-filtered (uncertain): {d['automod_filtered_count']} posts")
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
        print("Error:", d["error"])
        return
    _hr(f"SUBREDDIT COMPARISON  (ranked by {d.get('ranked_by', 'viral')})")
    print(
        f"{'subreddit':20} {'growth':>7} {'viral':>7} {'posts/day':>10} "
        f"{'comments':>9} {'removal':>8} {'safety':>9}  conf"
    )
    for p in d["ranked"]:
        conf = "low*" if p.get("low_confidence") else "ok"
        print(
            f"  r/{p['subreddit']:17} {p.get('growth_score', 0):>7} {p.get('viral_potential', 0):>7} "
            f"{p.get('posts_per_day', 0):>10} {p.get('median_comments', 0):>9} "
            f"{p['removal_rate']:>7.0%} {p.get('safety', '-'):>9}  {conf}"
        )
    if any(p.get("low_confidence") for p in d["ranked"]):
        print("  * low = many AutoMod-filtered posts; add creds for accuracy")
    for f in d.get("failed", []):
        print(f"  r/{f['subreddit']:17} — {f['error']}")
    if d.get("best_pick"):
        print(f"\nBest pick: r/{d['best_pick']}")
    print(f"({d['criteria']})")


def _print_draft(d: dict, tz: float = 0.0) -> None:
    if "error" in d:
        print("Error:", d["error"])
        return
    _hr(f"DRAFT EVALUATION · r/{d['subreddit']}")
    print(
        f"Acceptance: {d['acceptance_verdict']} (strictness {d.get('subreddit_strictness')}, "
        f"removal {d.get('removal_rate_estimate', 0):.0%})"
    )
    print(
        f"Performance: {d['performance_score']}/100 [{d['performance_band']}]  ·  "
        f"projected score ~{d['projected_score']} (sub avg {d['baseline_avg_score']})"
    )
    if d.get("clickbait_risk", 0) >= 0.4:
        print(f"Clickbait risk: {d['clickbait_risk']} (sub verdict: {d.get('sub_clickbait_verdict')})")
    va = d.get("viral_alignment")
    if va:
        print(f"Viral-recipe match: {va['alignment_pct']}% ({va['matched']}/{va['total']} traits)")
        if va.get("missing"):
            print(f"  Missing for viral: {', '.join(va['missing'])}")
        rc = va["recipe"]
        print(
            f"  Viral recipe: {rc['media']} / flair {rc['flair']} / {rc['time_block_utc']}"
            + (f" / words {rc['keywords']}" if rc.get("keywords") else "")
        )
        if rc.get("title_tags"):
            tags = ", ".join(f"[{t}]" for t in rc["title_tags"])
            print(f"  Tag hint: prefix your title with one of {tags}")
    if d.get("blocking_issues"):
        _hr("Blocking issues (likely removal)")
        for i in d["blocking_issues"]:
            print(f"  ✗ {i}")
    if d.get("warnings"):
        _hr("Warnings")
        for w in d["warnings"]:
            print(f"  ! {w}")
    if d.get("score_drivers"):
        _hr("Score drivers")
        for dr in d["score_drivers"]:
            print(f"  {dr['impact']:>16}  {dr['factor']}")
    if d.get("suggestions"):
        _hr("Suggestions to improve")
        for s in d["suggestions"]:
            print(f"  • {s}")
    hrs = d.get("best_posting_hours_utc", [])
    days = d.get("best_posting_days", [])
    if hrs or days:
        _hr("Recommended posting window")
        if hrs:
            print("  " + " / ".join(_fmt_hour(h["hour_utc"], tz) for h in hrs[:3]))
        if days:
            print("  Days: " + ", ".join(x["day"] for x in days[:2]))


def _print_traffic(d: dict) -> None:
    if "error" in d:
        print("Error:", d["error"])
        return
    s = d["signals"]
    print(f"\nr/{d['subreddit']} — activity: {d['activity_tier']}")
    print(
        f"  {s['posts_per_day_est']} posts/day · median {s['median_score']} upvotes · "
        f"{s['median_comments_per_post']} comments "
        f"(sample {s['sample']} over {s['span_days']}d)"
    )


def _print_fit(d: dict) -> None:
    if "error" in d:
        print("Error:", d["error"])
        return
    _hr("DRAFT FIT ACROSS SUBS (ranked by size-fair fit)")
    print(f"{'subreddit':20} {'fit/100':>8} {'reach~':>8} {'viral%':>7} {'removal':>8}  verdict")
    for r in d["ranked"]:
        vm = r.get("viral_match_pct")
        print(
            f"  r/{r['subreddit']:17} {r['fit_score']:>8} {r['projected_score']:>8} "
            f"{(str(vm) + '%') if vm is not None else '-':>7} {r['removal_rate']:>7.0%}  {r['acceptance_verdict']}"
        )
    for r in d.get("failed", []):
        print(f"  r/{r['subreddit']:17} — {r['error']}")
    if d.get("best_fit"):
        print(f"\nBest fit (size-fair): r/{d['best_fit']}  ·  Most reach: r/{d.get('most_reach')}")
    print(f"({d['note']})")


def _print_insight(d: dict) -> None:
    if "error" in d:
        print("Error:", d["error"])
        return
    print(f"\nr/{d['subreddit']} — insight (discussion depth): {d['insight_tier']}")
    print(
        f"  median comment {d['median_comment_chars']} chars / {d['median_comment_words']} words · "
        f"{d['substantive_ratio']:.0%} substantive (sample {d['sampled_comments']})"
    )


def _plan_markdown(plan: dict, tz: float) -> str:
    """Render a growth plan as Markdown for saving or sharing."""
    t = plan["target"]
    out = ["# Growth plan", "", f"## Target: r/{t['subreddit']}", ""]
    out.append(
        f"- growth **{t['growth_score']}** · viral {t['viral_potential']} · "
        f"{t['posts_per_day']} posts/day · {t['median_comments']} comments · "
        f"{t['removal_rate']:.0%} removed ({t['safety']})"
    )
    if t.get("insight_tier"):
        out.append(f"- discussion depth: **{t['insight_tier']}** ({t.get('substantive_ratio', 0):.0%} substantive)")
    if plan["avoided"]:
        out.append(f"- avoided (strict/low-confidence): {', '.join('r/' + s for s in plan['avoided'])}")

    if plan["also_consider"]:
        out += ["", "## Also worth posting to", ""]
        for p in plan["also_consider"]:
            out.append(
                f"- r/{p['subreddit']} — growth {p.get('growth_score', 0)}, "
                f"{p['removal_rate']:.0%} removed ({p.get('safety')})"
            )

    rc = plan.get("recipe")
    if rc:
        out += ["", "## What to post (viral recipe)", ""]
        out.append(f"- Format: {rc['media_type']['value']}")
        if rc["flair"]["value"]:
            out.append(f"- Flair: {rc['flair']['value']}")
        tag = rc.get("title_tag", {})
        if tag.get("share", 0) >= 0.3 and tag.get("common"):
            out.append(f"- Title tag: {', '.join('[' + x + ']' for x in tag['common'])}")
        out.append(f"- Length: ~{rc['title']['median_char_length']} chars, no clickbait")
        if rc.get("keywords"):
            out.append(f"- Keywords: {', '.join(rc['keywords'][:5])}")
    if plan["best_posting_hours_utc"]:
        out += ["", "## When to post", ""]
        out.append("- " + " / ".join(_fmt_hour(h["hour_utc"], tz) for h in plan["best_posting_hours_utc"]))
    if plan["best_posting_days"]:
        out.append("- Days: " + ", ".join(x["day"] for x in plan["best_posting_days"]))
    out += ["", f"_{plan.get('disclaimer', '')}_"]
    return "\n".join(out)


def _run_plan(args, reddit) -> None:
    """Growth planner: rank subs, pick the safest strong one, print its recipe."""
    plan = build_growth_plan(args.subreddits, reddit, args.window)
    if "error" in plan:
        print("Could not build a plan:", plan["error"])
        return
    if getattr(args, "md", False):
        print(_plan_markdown(plan, args.tz))
        return

    t = plan["target"]
    _hr("GROWTH PLAN")
    print(f"Target: r/{t['subreddit']}")
    print(
        f"  growth {t['growth_score']} · viral {t['viral_potential']} · "
        f"{t['posts_per_day']} posts/day · {t['median_comments']} comments · "
        f"{t['removal_rate']:.0%} removed ({t['safety']})"
    )
    if t.get("insight_tier"):
        print(f"  discussion depth (insight): {t['insight_tier']} ({t.get('substantive_ratio', 0):.0%} substantive)")
    if plan["avoided"]:
        print(f"  Avoided (strict/low-confidence): {', '.join('r/' + s for s in plan['avoided'])}")

    if plan["also_consider"]:
        _hr("Also worth posting to (safe, tailor per sub)")
        for p in plan["also_consider"]:
            print(
                f"  r/{p['subreddit']:18} growth {p.get('growth_score', 0):>6} · "
                f"{p['removal_rate']:.0%} removed ({p.get('safety')})"
            )

    rc = plan.get("recipe")
    if rc:
        _hr("What to post (viral recipe)")
        print(f"  Format : {rc['media_type']['value']}")
        if rc["flair"]["value"]:
            print(f"  Flair  : {rc['flair']['value']}")
        tag = rc.get("title_tag", {})
        if tag.get("share", 0) >= 0.3 and tag.get("common"):
            print(f"  Tag    : {', '.join('[' + x + ']' for x in tag['common'])}")
        print(f"  Length : ~{rc['title']['median_char_length']} chars, no clickbait")
        if rc.get("keywords"):
            print(f"  Words  : work in {', '.join(rc['keywords'][:5])}")
    if plan["best_posting_hours_utc"]:
        _hr("When to post")
        print("  " + " / ".join(_fmt_hour(h["hour_utc"], args.tz) for h in plan["best_posting_hours_utc"]))
    if plan["best_posting_days"]:
        print("  Days: " + ", ".join(x["day"] for x in plan["best_posting_days"]))


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="reddit-analyzer", description="Analyze subreddits and post patterns.")
    p.add_argument("--json", action="store_true", help="Emit raw JSON instead of a formatted report")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("patterns", help="What makes posts perform in a subreddit")
    sp.add_argument("subreddit")
    sp.add_argument("--time", default="month", choices=["day", "week", "month", "year", "all"])
    sp.add_argument("--limit", type=int, default=200)
    sp.add_argument(
        "--metric",
        default="score",
        choices=["score", "comments", "discussion", "quality"],
        help="score=upvotes, discussion=comments/upvote (anti-clickbait), quality=clickbait-damped",
    )
    sp.add_argument(
        "--tz", type=float, default=0.0, help="Local UTC offset in hours to also show posting times in (e.g. 7 for WIB)"
    )

    sa = sub.add_parser("acceptance", help="Removal rate + what gets nuked")
    sa.add_argument("subreddit")
    sa.add_argument("--sample", type=int, default=200)

    st_ = sub.add_parser("traffic", help="Estimate a subreddit's activity (posts/day)")
    st_.add_argument("subreddit")
    st_.add_argument("--window", default="30d")

    si = sub.add_parser("insight", help="Measure a subreddit's discussion depth (comment substance)")
    si.add_argument("subreddit")
    si.add_argument("--after", default="3d")

    sc = sub.add_parser("compare", help="Rank subreddits by viral potential or opportunity")
    sc.add_argument("subreddits", nargs="+")
    sc.add_argument("--window", default="60d")
    sc.add_argument("--sample", type=int, default=200)
    sc.add_argument(
        "--rank-by", dest="rank_by", default="growth", choices=["growth", "viral", "opportunity", "insight"]
    )

    sr = sub.add_parser("report", help="Full report: acceptance + patterns for a subreddit")
    sr.add_argument("subreddit")
    sr.add_argument("--time", default="month", choices=["day", "week", "month", "year", "all"])
    sr.add_argument("--tz", type=float, default=0.0)

    spl = sub.add_parser("plan", help="Growth plan: pick the best safe sub and its viral recipe")
    spl.add_argument("subreddits", nargs="+")
    spl.add_argument("--window", default="30d")
    spl.add_argument("--tz", type=float, default=0.0)
    spl.add_argument("--md", action="store_true", help="Output the plan as Markdown (for saving/sharing)")

    sd = sub.add_parser("draft", help="Evaluate a post draft")
    sd.add_argument("subreddit")
    sd.add_argument("--title", required=True)
    sd.add_argument("--body", default="")
    sd.add_argument("--type", default="text", dest="post_type")
    sd.add_argument("--flair", default=None)
    sd.add_argument("--tz", type=float, default=0.0, help="Local UTC offset for posting times")

    sf = sub.add_parser("fit", help="Score one draft across subs, ranked by size-fair fit")
    sf.add_argument("subreddits", nargs="+")
    sf.add_argument("--title", required=True)
    sf.add_argument("--type", default="text", dest="post_type")
    sf.add_argument("--flair", default=None)

    args = p.parse_args(argv)
    reddit = _get_reddit()
    if reddit is None and args.cmd in {"patterns", "acceptance", "compare", "draft"}:
        print("(no Reddit credentials — using archive mode)", file=sys.stderr)

    if args.cmd == "patterns":
        result = analyze_post_patterns(args.subreddit, reddit, "top", args.time, args.limit, "auto", args.metric)
        printer = _print_patterns
    elif args.cmd == "acceptance":
        result = analyze_acceptance(args.subreddit, reddit, args.sample)
        printer = _print_acceptance
    elif args.cmd == "compare":
        result = compare_subreddits(args.subreddits, args.window, args.sample, args.rank_by)
        printer = _print_compare
    elif args.cmd == "draft":
        result = evaluate_draft(args.subreddit, args.title, reddit, args.body, args.post_type, args.flair)
        printer = _print_draft
    elif args.cmd == "traffic":
        result = estimate_activity_archive(args.subreddit, args.window)
        printer = _print_traffic
    elif args.cmd == "insight":
        result = analyze_insight(args.subreddit, args.after)
        printer = _print_insight
    elif args.cmd == "fit":
        result = evaluate_draft_across(args.subreddits, args.title, reddit, "", args.post_type, args.flair)
        printer = _print_fit
    elif args.cmd == "plan":
        _run_plan(args, reddit)
        return 0
    elif args.cmd == "report":
        acc = analyze_acceptance(args.subreddit, reddit)
        pat = analyze_post_patterns(args.subreddit, reddit, "top", args.time, 200, "auto")
        if args.json:
            print(json.dumps({"acceptance": acc, "patterns": pat}, indent=2, default=str))
        else:
            _print_acceptance(acc)
            _print_patterns(pat, args.tz)
        return 0
    else:  # pragma: no cover
        p.error("unknown command")

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    elif args.cmd == "patterns":
        _print_patterns(result, getattr(args, "tz", 0.0))
    elif args.cmd == "draft":
        _print_draft(result, getattr(args, "tz", 0.0))
    else:
        printer(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
