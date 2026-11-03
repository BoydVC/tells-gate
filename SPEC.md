# SPEC: Tells Gate

## One line
A shared `banned.md` of AI-writing tells plus a checker that scores any draft 0–100, flags each tell with its span, and suggests a rewrite. It runs as a CLI, a small live web page, and an HTTP gate (`POST /check`) that X Post Queue can call before Approve.

## Why
- @AISystems_hq and @Zephyr_hg keep a banned.md their bots must pass before a draft reaches them. Their point is that a list with examples beats a vague "sound human" note, because a checker can test against a list.
- Boyd posts as himself, and the draft-as-boyd voice matters. Every writing bot (X Post Queue, Family Times, Brief Forge) can share one gate.
- It is small, testable and easy to demo: a before/after GIF of a sloppy draft going from red to green.

## Users and outcome
- **Boyd** pastes a draft into the page, sees the tells highlighted live with why and fix, and clicks "Apply suggested rewrite".
- **Bots** call `tells-gate check --json` or `POST /check` and either block or rewrite before a human sees the draft.

## Scope (v1)
1. `banned.md`: rules with `id` (TG###), `name`, `why`, `fix`, `weight`, `cap`, `example`, and either `pattern:` regexes or a `detector:` name. At least the 9 tells from the source posts, plus hedges, filler openers/closers, em-dash density, triad lists and rhetorical Q&A.
2. Checker: deterministic and offline. It masks code, URLs and HTML. Scores are density-scaled for long docs. Verdicts: pass ≥ 80, warn 60–79, fail < 60.
3. Rewrite: a mechanical cleanup per rule (delete, replace, keep the Y of "not X, it's Y"). It must never make a score worse, and it must leave clean text byte-identical.
4. Interfaces: the CLI (`check [--json] [--min-score N] [--llm] files|-`, `rules`, `serve`), the web page with live highlighting, and `POST /check` returning `gate: allow|block`.
5. LLM pass: behind `--llm` / `{"llm": true}`. It's a stub offline and calls `TELLS_GATE_LLM_URL` when that's set.
6. Integration: an INTEGRATION.md patch for X Post Queue approve. It fails open and supports `force`.

Out of scope: auto-posting, any account access, anything KPD, and style rules about Boyd's personal voice (that's a v2 "your own tells" step).

## Core types
- `Rule {id, name, why, fix, weight, cap, patterns[], detector?, example}`
- `Hit {rule, name, start, end, text, why, fix, suggestion, line, col}` with offsets in Unicode code points
- `Report {score, verdict, words, hits[], by_rule, penalties, rewrite, llm?}` (+ `gate` over HTTP)

## Acceptance
- Every rule catches its own `example`. A fixed good corpus scores 100. The bad samples fail.
- The rewrite lifts each bad sample by more than 30 points.
- On real public text, the BoydVC public READMEs average above 90 with no fails (no false-positive storm).
- `python3 -m unittest` is green with 35+ tests. demo.gif uses synthetic text only. No network calls in tests.

## Prototype status (box, 2026-11-03)
Built in `/workspace/tokenmax/tells-gate`: 17 rules, 38 tests green. 119 public BoydVC READMEs averaged 96.6 (min 84, 0 warn, 0 fail). demo.gif is rendered by `make_demo.py`.
