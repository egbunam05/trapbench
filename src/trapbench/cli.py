"""Command line: lint, grade, verify, init, rules."""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

from . import __version__
from .grade import CORRECT, INCORRECT, NOT_ATTEMPTED, grade_all, summarize
from .lint import RULES, lint
from .schema import TEMPLATE, TaskFileError, load_responses, load_tasks
from .verify import VERIFY_RULES, verify_tasks


def _print_issues(issues, n_tasks: int, as_json: bool) -> int:
    errors = sum(i.severity == "error" for i in issues)
    warnings = len(issues) - errors
    if as_json:
        print(json.dumps([asdict(i) for i in issues], indent=2, ensure_ascii=False))
    else:
        for issue in issues:
            print(issue)
        print(f"{n_tasks} task(s): {errors} error(s), {warnings} warning(s)")
    return errors


def cmd_lint(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    issues = lint(tasks, ignore=(args.ignore or "").split(","))
    errors = _print_issues(issues, len(tasks), args.json)
    warnings = len(issues) - errors
    return 1 if errors or (args.strict and warnings) else 0


def cmd_grade(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    responses = load_responses(args.answers)
    grades, unknown = grade_all(tasks, responses, args.mode, args.max_words, args.keep_accents)
    stats = summarize(grades)
    if args.json:
        print(json.dumps({"summary": stats, "grades": [asdict(g) for g in grades], "unknown_ids": unknown},
                         indent=2, ensure_ascii=False))
        return 0
    print(f"mode: {args.mode}   tasks: {stats['n']}")
    print(f"  correct        {stats['correct']:>3}  ({stats['accuracy']:.0%} of all)")
    print(f"  incorrect      {stats['incorrect']:>3}")
    print(f"  not attempted  {stats['not_attempted']:>3}")
    print(f"  accuracy given attempted: {stats['accuracy_given_attempted']:.0%}")
    print(f"  F-score (harmonic mean of the two accuracies): {stats['f_score']:.2f}")
    if unknown:
        print(f"warning: {len(unknown)} response id(s) match no task: {', '.join(unknown)}")
    if args.details:
        print()
        for g in grades:
            mark = {CORRECT: "ok  ", INCORRECT: "FAIL", NOT_ATTEMPTED: "skip"}[g.verdict]
            print(f"  {mark} {g.id}: {g.reason}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.tasks)
    issues = verify_tasks(tasks, timeout=args.timeout, delay=args.delay)
    errors = _print_issues(issues, len(tasks), args.json)
    return 1 if errors else 0


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"error: {path} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    path.write_text(TEMPLATE, encoding="utf-8")
    print(f"wrote {path}. Edit it, then run: trapbench lint {path}")
    return 0


def cmd_rules(_: argparse.Namespace) -> int:
    for code, (severity, title) in RULES.items():
        print(f"{code}  {severity:<5}  {title}")
    descriptions = {"V001": "cited page is unreachable", "V002": "quote not found on the cited page",
                    "V003": "answer not found on the cited page"}
    for code, severity in VERIFY_RULES.items():
        print(f"{code}  {severity:<5}  {descriptions[code]}  (trapbench verify)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="trapbench", description=__doc__)
    parser.add_argument("--version", action="version", version=f"trapbench {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("lint", help="check tasks for authoring mistakes (offline)")
    p.add_argument("tasks")
    p.add_argument("--strict", action="store_true", help="fail on warnings too")
    p.add_argument("--ignore", help="comma-separated rule codes to skip, e.g. W102,W106")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("grade", help="grade model answers against the answer keys (offline)")
    p.add_argument("tasks")
    p.add_argument("answers", help='JSONL of {"id": ..., "response": ...}')
    p.add_argument("--mode", choices=["strict", "lenient"], default="lenient")
    p.add_argument("--max-words", type=int, default=30, help="lenient mode: longer responses are incorrect")
    p.add_argument("--keep-accents", action="store_true", help="treat 'ị' and 'i' as different letters")
    p.add_argument("--details", action="store_true")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_grade)

    p = sub.add_parser("verify", help="fetch each source and confirm the quote is on the page (needs network)")
    p.add_argument("tasks")
    p.add_argument("--timeout", type=float, default=15.0)
    p.add_argument("--delay", type=float, default=1.0, help="seconds between requests")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("init", help="write a starter tasks file")
    p.add_argument("path", nargs="?", default="tasks.jsonl")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("rules", help="list every lint rule")
    p.set_defaults(func=cmd_rules)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (TaskFileError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
