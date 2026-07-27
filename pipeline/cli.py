#!/usr/bin/env python3
"""wom - one entry point for the pipeline.

Wraps what already existed as four scattered invocations (`python -m
core.runner`, `python -m sources.registry`, `uvicorn review.app:app`) and adds
the one that was missing: running a scoped-crawler source without the web UI.

Subcommands are deliberately thin. Each one parses arguments and calls the
same function the module already exposed - the lifecycle lives in core/, not
here, so `wom run` and a dashboard "Run" click cannot drift apart.

Imports are done inside each subcommand rather than at module level: pulling
in fitz, fastapi and trafilatura costs about a second, and `wom --help` or a
mistyped subcommand should not pay it.
"""

import argparse
import sys


def _cmd_sources(args: argparse.Namespace) -> int:
    """Every configured source and which runner owns it. `wom run` dispatches
    on exactly this, so if a source is missing here it is missing there."""
    from core import crawl_config
    from core.runner import lade_quellen_config

    crawl = crawl_config.load_all_crawl_sources()
    batch = lade_quellen_config()
    if not crawl and not batch:
        print("No sources configured. Add one to data/_sources/.", file=sys.stderr)
        return 1

    rows = [(sid, "crawl", s.category, s.seed_url) for sid, s in crawl.items()]
    rows += [(sid, "batch", c.get("kategorie", ""), c.get("url", "")) for sid, c in batch.items()]

    width = max(len(sid) for sid, *_ in rows)
    for source_id, kind, category, url in sorted(rows):
        print(f"{source_id:<{width}}  {kind:<5}  {category:<16}  {url}")
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    """Fetch a source and stage its candidates for review.

    Both runners end the same way - already-reviewed candidates are written
    straight to data/, everything else waits in staging/ for `wom review`.
    Neither writes an unreviewed candidate to data/.
    """
    from core import crawl_config
    from core.runner import lade_quellen_config, parse_params
    from core.runner import run as run_batch

    if args.source_id in lade_quellen_config():
        try:
            params = parse_params(args.params)
        except ValueError as e:
            print(f"[wom] {e}", file=sys.stderr)
            return 2
        return run_batch(args.source_id, params)

    crawl = crawl_config.load_all_crawl_sources()
    if args.source_id not in crawl:
        known = sorted([*crawl, *lade_quellen_config()])
        print(f"[wom] Unknown source '{args.source_id}'. Known: {', '.join(known) or '(none)'}", file=sys.stderr)
        return 1
    if args.params:
        print("[wom] A crawl source takes no --key params; its scope is its config file.", file=sys.stderr)
        return 2

    from core.crawl_runner import run as run_crawl

    def report(update: dict) -> None:
        print(f"[{update['phase']}] {update['detail']}", file=sys.stderr)

    result = run_crawl(crawl[args.source_id], on_progress=report)
    print(
        f"[wom] {result['reconfirmed']} already reviewed, {result['needs_review']} waiting in staging/",
        file=sys.stderr,
    )
    return 0


def _cmd_review(args: argparse.Namespace) -> int:
    """Serve the review app - the approval step, not just a view of it."""
    import uvicorn

    from review.app import app

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _cmd_registry(args: argparse.Namespace) -> int:
    from sources import registry

    return registry.run(args.entity_class)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wom",
        description="Wann-O-Meter pipeline: fetch sources, review candidates, publish to data/.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("sources", help="list configured sources and which runner owns each")
    p.set_defaults(func=_cmd_sources)

    p = sub.add_parser("run", help="fetch one source and stage its candidates")
    p.add_argument("source_id", help="as listed by `wom sources`")
    p.add_argument(
        "params",
        nargs=argparse.REMAINDER,
        help="--key value pairs for a batch source, e.g. --jahr 2028",
    )
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("review", help="serve the review app")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=_cmd_review)

    p = sub.add_parser("registry", help="fetch a Wikidata entity registry (crawl seeds)")
    p.add_argument("entity_class", help="a key in pipeline/config/registries.yaml")
    p.set_defaults(func=_cmd_registry)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
