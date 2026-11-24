"""Command line: rtharness run | compare | list"""
from __future__ import annotations

import argparse
import json
import os
import sys

from .agent import Defenses
from .attacks import load_attacks
from .backends import make_backend
from .mutators import MUTATORS
from .report import render_compare, render_markdown, save_json
from .runner import run_suite

DEFAULT_ATTACKS = os.path.join(os.path.dirname(__file__), "..", "..", "attacks")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="rtharness", description="Red-team harness for LLM agents")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run attacks against a backend")
    r.add_argument("--backend", choices=["mock", "anthropic", "openai"], default="mock")
    r.add_argument("--model", help="model name (required for openai backend)")
    r.add_argument("--base-url", help="API base URL (openai-compatible servers, e.g. Ollama)")
    r.add_argument("--defense", default="none", help="none | spotlight | policy | spotlight+policy")
    r.add_argument("--attacks", default=DEFAULT_ATTACKS, help="YAML file or directory")
    r.add_argument("--mutators", default=",".join(MUTATORS), help="comma-separated mutator names")
    r.add_argument("--trials", type=int, default=1, help="repeat each case (use >1 for real models)")
    r.add_argument("--seed", type=int, default=0)
    r.add_argument("--out", default="results/run", help="output prefix (writes .json and .md)")

    c = sub.add_parser("compare", help="before/after table from two result JSON files")
    c.add_argument("before")
    c.add_argument("after")

    sub.add_parser("list", help="list attacks and mutators").add_argument("--attacks", default=DEFAULT_ATTACKS)

    args = p.parse_args(argv)

    if args.cmd == "list":
        attacks = load_attacks(args.attacks)
        for a in attacks:
            print(f"{a.id}  {a.category:<20} {a.title}")
        print(f"\n{len(attacks)} base attacks; mutators: {', '.join(MUTATORS)}")
        return 0

    if args.cmd == "compare":
        with open(args.before) as f1, open(args.after) as f2:
            print(render_compare(json.load(f1), json.load(f2)))
        return 0

    attacks = load_attacks(args.attacks)
    backend = make_backend(args.backend, args.model, args.base_url, args.seed)
    defenses = Defenses.parse(args.defense)
    mutators = [m.strip() for m in args.mutators.split(",") if m.strip()]

    def progress(done, total):
        if done % 10 == 0 or done == total:
            print(f"\r{done}/{total} runs", end="", file=sys.stderr)

    run = run_suite(backend, attacks, defenses, mutators, args.trials, args.seed, progress)
    print(file=sys.stderr)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    save_json(run, args.out + ".json")
    md = render_markdown(run)
    with open(args.out + ".md", "w", encoding="utf-8") as fh:
        fh.write(md)
    print(md.split("\n## Successful")[0])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
