"""Command-line entry point: load -> triage -> report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .providers import ProviderUnavailable, get_provider
from .report import write_html, write_json
from .triage import RunStats, load_emails, run_triage


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inbox-triage",
        description="Classify a batch of customer emails, score urgency, and draft replies.",
    )
    parser.add_argument("input", help="Path to a .csv or .mbox file of emails")
    parser.add_argument(
        "--provider",
        choices=("anthropic", "claude-cli", "mock"),
        default="anthropic",
        help="LLM backend. 'mock' is an offline keyword-heuristic demo mode (default: anthropic, "
        "falls back to mock if the SDK or API key is missing)",
    )
    parser.add_argument("--model", default=None, help="Override the Anthropic model id")
    parser.add_argument("--batch-size", type=int, default=5, help="Emails per API call (default: 5)")
    parser.add_argument("--out", default="triage_output", help="Output directory (default: triage_output)")
    parser.add_argument("--limit", type=int, default=None, help="Only process the first N emails")
    parser.add_argument("--yes", action="store_true", help="Skip the cost-estimate confirmation prompt")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        emails = load_emails(args.input)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if args.limit:
        emails = emails[: args.limit]
    if not emails:
        print("error: no emails found in input", file=sys.stderr)
        return 2

    provider = _resolve_provider(args)

    if provider.name == "anthropic":
        from .providers.anthropic_provider import AnthropicProvider

        est = AnthropicProvider.estimate_cost_usd(emails, args.batch_size)
        print(f"Estimated cost for {len(emails)} emails: ~${est:.4f} ({provider.model})")
        if not args.yes and sys.stdin.isatty():
            if input("Proceed? [y/N] ").strip().lower() not in ("y", "yes"):
                print("Aborted.")
                return 1

    print(f"Triaging {len(emails)} emails with provider '{provider.name}'...")
    results = run_triage(
        emails,
        provider,
        batch_size=args.batch_size,
        on_progress=lambda done, total: print(f"  {done}/{total} processed"),
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    html_path = out_dir / "report.html"
    json_path = out_dir / "results.json"
    stats = RunStats.from_results(results)
    write_html(results, stats, html_path, provider.name)
    write_json(results, json_path)

    _print_summary(stats, provider)
    print(f"\nHTML report: {html_path}")
    print(f"JSON export: {json_path}")
    return 0


def _resolve_provider(args):
    try:
        return get_provider(args.provider, model=args.model)
    except ProviderUnavailable as exc:
        print(f"note: anthropic provider unavailable ({exc})")
        print("note: falling back to --provider mock (offline heuristics, not an LLM)\n")
        return get_provider("mock")


def _print_summary(stats: RunStats, provider) -> None:
    print(f"\n=== Summary ({stats.total} messages) ===")
    print("By category:")
    for cat, n in sorted(stats.by_category.items(), key=lambda kv: -kv[1]):
        print(f"  {cat:<16} {n:>3}  {'#' * n}")
    print("By urgency:")
    for level in range(5, 0, -1):
        n = stats.by_urgency.get(level, 0)
        print(f"  {level} {'(critical)' if level == 5 else '':<11} {n:>3}  {'#' * n}")
    print("By sentiment:")
    for s in ("positive", "neutral", "negative"):
        print(f"  {s:<16} {stats.by_sentiment.get(s, 0):>3}")
    if stats.high_urgency:
        print("Needs attention first:")
        for item in stats.high_urgency[:5]:
            print(f"  [{item.result.urgency}] {item.email.subject}  ({item.email.sender})")
    if provider.name == "anthropic":
        u = provider.usage
        print(
            f"API usage: {u.input_tokens:,} in / {u.output_tokens:,} out tokens"
            f"  ->  ${provider.cost_usd():.4f}"
        )
    elif provider.name == "claude-cli":
        print("API cost: $0.00 (ran through the local Claude Code CLI, subscription auth)")
    else:
        print("API cost: $0.00 (mock provider, no API calls made)")


if __name__ == "__main__":
    raise SystemExit(main())



