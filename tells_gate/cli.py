"""tells-gate CLI: check | rules | serve."""
from __future__ import annotations

import argparse
import difflib
import json
import sys

from .core import check, load_rules

RED, YEL, GRN, DIM, OFF = "\033[31m", "\033[33m", "\033[32m", "\033[2m", "\033[0m"


def _headline(path: str, rep, color: bool) -> str:
    c = (lambda s, k: f"{k}{s}{OFF}") if color else (lambda s, k: s)
    col = GRN if rep.verdict == "pass" else YEL if rep.verdict == "warn" else RED
    return f"{path}: {c(str(rep.score), col)}/100 {c(rep.verdict.upper(), col)}  ({rep.words} words, {len(rep.hits)} tells)"


def _fmt(path: str, text: str, rep, color: bool) -> str:
    c = (lambda s, k: f"{k}{s}{OFF}") if color else (lambda s, k: s)
    lines = [_headline(path, rep, color)]
    for h in rep.hits:
        lines.append(f"  {path}:{h.line}:{h.col} {c(h.rule, YEL)} {h.name}: \"{h.text.strip()[:70]}\"")
        lines.append(c(f"      why: {h.why}", DIM))
        lines.append(f"      fix: {h.fix}  ->  {h.suggestion}")
    if rep.rewrite != text:
        lines.append(c("  suggested rewrite:", DIM))
        lines += ["    " + l for l in rep.rewrite.splitlines()] or ["    (empty)"]
    return "\n".join(lines)


def _diff(path: str, before: str, after: str, color: bool) -> str:
    label = "stdin" if path == "-" else path
    out = []
    for line in difflib.unified_diff(before.splitlines(keepends=True), after.splitlines(keepends=True),
                                      f"a/{label}", f"b/{label}"):
        if not line.endswith("\n"):
            line += "\n\\ No newline at end of file\n"
        if color and line[:1] in "+-" and line[:3] not in ("+++", "---"):
            line = f"{GRN if line[0] == '+' else RED}{line.rstrip(chr(10))}{OFF}\n"
        out.append(line)
    return "".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="tells-gate", description="Score drafts for AI-writing tells (banned.md).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check files (or - for stdin)")
    c.add_argument("files", nargs="+")
    c.add_argument("--json", action="store_true")
    c.add_argument("--diff", action="store_true", help="print the rewrite as a unified diff (score line goes to stderr)")
    c.add_argument("--banned", help="path to banned.md")
    c.add_argument("--min-score", type=int, default=None, help="exit 1 if any score is below this (default: verdict fail)")
    c.add_argument("--llm", action="store_true", help="run optional LLM pass (stubbed)")
    c.add_argument("--no-color", action="store_true")
    r = sub.add_parser("rules", help="list rules")
    r.add_argument("--banned")
    s = sub.add_parser("serve", help="web page + POST /check")
    s.add_argument("--port", type=int, default=4350)
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--banned")
    a = ap.parse_args(argv)

    if a.cmd == "rules":
        for rule in load_rules(a.banned):
            print(f"{rule.id} {rule.name:18} w={rule.weight:g} cap={rule.cap:g}  {rule.rewriter:14} {rule.fix}")
        return 0
    if a.cmd == "serve":
        from .server import serve
        serve(a.host, a.port, a.banned)
        return 0

    rules = load_rules(a.banned)
    results, bad = [], False
    for f in a.files:
        text = sys.stdin.read() if f == "-" else open(f, encoding="utf-8").read()
        rep = check(text, rules, llm=a.llm)
        failed = rep.score < a.min_score if a.min_score is not None else rep.verdict == "fail"
        bad |= failed
        results.append((f, text, rep))
    if a.json:
        out = [dict(file=f, **rep.to_dict(), **({"diff": _diff(f, text, rep.rewrite, False) or None} if a.diff else {}))
               for f, text, rep in results]
        print(json.dumps(out[0] if len(out) == 1 else out, indent=2, ensure_ascii=False))
    elif a.diff:
        for f, text, rep in results:
            print(_headline(f, rep, sys.stderr.isatty() and not a.no_color), file=sys.stderr)
            sys.stdout.write(_diff(f, text, rep.rewrite, sys.stdout.isatty() and not a.no_color))
    else:
        color = sys.stdout.isatty() and not a.no_color
        print("\n\n".join(_fmt(f, text, rep, color) for f, text, rep in results))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
