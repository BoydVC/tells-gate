"""Core: parse banned.md, detect tells, score, and rewrite. Stdlib only."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterable, Literal, NamedTuple

DEFAULT_BANNED = Path(os.environ.get("TELLS_GATE_BANNED", Path(__file__).resolve().parent.parent / "banned.md"))
PASS_AT = 80
WARN_AT = 60

Span = tuple[int, int]


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    why: str
    fix: str
    weight: float
    cap: float
    patterns: tuple[re.Pattern, ...] = ()
    detector: str | None = None
    example: str = ""
    rewriter: str = "none"

    @property
    def rewriter_note(self) -> str:
        return REWRITERS[self.rewriter].note


@dataclass
class Hit:
    rule: str
    name: str
    start: int
    end: int
    text: str
    why: str
    fix: str
    suggestion: str
    line: int = 0
    col: int = 0


@dataclass
class Report:
    score: int
    verdict: str  # pass | warn | fail
    words: int
    hits: list[Hit] = field(default_factory=list)
    by_rule: dict[str, int] = field(default_factory=dict)
    penalties: dict[str, float] = field(default_factory=dict)
    rewrite: str = ""
    llm: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------- parsing
_RULE_HEAD = re.compile(r"^##\s+(TG\d{3})\s+(\S+)\s*$")
_FIELD = re.compile(r"^-\s+(why|fix|weight|cap|pattern|detector|example|case|rewriter):\s?(.*)$")


def parse_banned(md: str) -> list[Rule]:
    rules: list[Rule] = []
    cur: dict | None = None

    def flush():
        if not cur:
            return
        flags = 0 if cur.get("case") == "sensitive" else re.IGNORECASE
        pats = tuple(re.compile(p, flags | re.MULTILINE) for p in cur["patterns"])
        if not pats and not cur.get("detector"):
            raise ValueError(f"{cur['id']}: needs pattern: or detector:")
        if cur.get("detector") and cur["detector"] not in DETECTORS:
            raise ValueError(f"{cur['id']}: unknown detector {cur['detector']}")
        rewriter = cur.get("rewriter", "none")
        if rewriter not in REWRITERS:
            raise ValueError(f"{cur['id']}: unknown rewriter {rewriter}")
        rules.append(Rule(cur["id"], cur["name"], cur.get("why", ""), cur.get("fix", ""),
                          float(cur.get("weight", 5)), float(cur.get("cap", 15)), pats,
                          cur.get("detector"), cur.get("example", ""), rewriter))

    for raw in md.splitlines():
        m = _RULE_HEAD.match(raw.strip())
        if m:
            flush()
            cur = {"id": m.group(1), "name": m.group(2), "patterns": []}
            continue
        if cur is None:
            continue
        f = _FIELD.match(raw.strip())
        if not f:
            continue
        k, v = f.group(1), f.group(2).strip()
        if k == "pattern":
            cur["patterns"].append(v)
        else:
            cur[k] = v
    flush()
    ids = [r.id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule ids in banned.md")
    return rules


def load_rules(path: str | Path | None = None) -> list[Rule]:
    return parse_banned(Path(path or DEFAULT_BANNED).read_text(encoding="utf-8"))


# ---------------------------------------------------------------- masking
_CODE_FENCE = re.compile(r"```.*?(?:```|\Z)", re.S)
_INLINE = re.compile(r"`[^`\n]*`")
_URL = re.compile(r"https?://\S+")
_HTML = re.compile(r"<[^>\n]+>")


def _fold_apostrophes(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'")


def mask(text: str, fill: str = " ") -> str:
    def blank(m):
        return re.sub(r"[^\n]", fill, m.group(0))
    out = _CODE_FENCE.sub(blank, text)
    out = _INLINE.sub(blank, out)
    out = _HTML.sub(blank, out)
    # keep URLs visible to the arrow rule: mask only the URL body after the scheme
    out = _URL.sub(lambda m: m.group(0)[:8] + fill * (len(m.group(0)) - 8), out)
    return out


# ---------------------------------------------------------------- detectors
HYPE_ADJ = {
    "powerful", "seamless", "game-changing", "revolutionary", "cutting-edge", "innovative",
    "robust", "transformative", "groundbreaking", "next-level", "effortless", "intuitive",
    "stunning", "incredible", "unparalleled", "world-class", "insane", "mind-blowing",
    "magical", "elegant", "blazing-fast", "lightning-fast", "scalable", "holistic", "dynamic",
}
ABSTRACT = {
    "speed", "clarity", "confidence", "focus", "growth", "trust", "efficiency", "simplicity",
    "power", "flexibility", "scale", "impact", "innovation", "productivity", "creativity",
    "connection", "freedom", "control", "insight", "insights", "value", "quality", "purpose",
    "passion", "community", "collaboration", "transparency", "accountability", "momentum",
}
ABBREVIATIONS = {"dr", "mr", "mrs", "ms", "st", "fig", "eq", "no", "vs", "jr", "sr"}
_BEAT_RUN = re.compile(r"(?:(?<=^)|(?<=[\s>]))(?:[A-Z][\w'’-]*(?: [\w'’-]+)?[.!](?: |(?=\s|$)))+", re.M)
_BEAT = re.compile(r"[A-Z][\w'’-]*(?: [\w'’-]+)?[.!]")


def _between_digits(t: str, s: int, e: int) -> bool:
    return bool(re.search(r"\d[ \t]*\Z", t[max(0, s - 8):s]) and re.match(r"[ \t]*\d", t[e:e + 8]))


def _breaks_the_run(words: list[str]) -> bool:
    if len(words) == 1 and words[0].lower() in ABBREVIATIONS:
        return True
    return any(len(re.sub(r"[^A-Za-z]", "", w)) < 3 for w in words)


def _cannot_open_a_run(streak: list[Span], after_abbrev: bool) -> bool:
    return not streak and after_abbrev


def det_triad_fragments(t: str) -> list[Span]:
    # three or more consecutive 1-2 word sentences: "Write. Edit. Ship."
    out: list[Span] = []
    for run in _BEAT_RUN.finditer(t):
        streak: list[Span] = []
        after_abbrev = False
        for b in _BEAT.finditer(t, run.start(), run.end()):
            words = b.group()[:-1].split()
            abbrev = len(words) == 1 and words[0].lower() in ABBREVIATIONS
            if _breaks_the_run(words) or _cannot_open_a_run(streak, after_abbrev):
                if len(streak) >= 3:
                    out.append((streak[0][0], streak[-1][1]))
                streak = []
            else:
                streak.append(b.span())
            after_abbrev = abbrev
        if len(streak) >= 3:
            out.append((streak[0][0], streak[-1][1]))
    return out


def det_triad_list(t: str) -> list[Span]:
    pat = re.compile(r"\b([A-Za-z-]+), ([A-Za-z-]+),? (?:and|&) ([A-Za-z-]+)\b")
    out = []
    for m in pat.finditer(t):
        words = [w.lower() for w in m.groups()]
        if sum(w in ABSTRACT or w in HYPE_ADJ for w in words) >= 2:
            out.append(m.span())
    return out


def det_adjective_pile(t: str) -> list[Span]:
    pat = re.compile(r"\b([A-Za-z-]+)(?:,\s*| and )([A-Za-z-]+)(?:(?:,\s*(?:and )?| and )([A-Za-z-]+))?\b")
    out = []
    for m in pat.finditer(t):
        words = [w.lower() for w in m.groups() if w]
        if sum(w in HYPE_ADJ for w in words) >= 2:
            out.append(m.span())
    return out


_LIST_LABEL_DASH = re.compile(
    r"(?m)^\s*(?:[-*+]|\d+\.)\s+(?:\*\*[^*\n]{1,60}\*\*|`[^`\n]{1,60}`|\S[^—–\n]{0,40}?)\s*[—–]"
)


def det_em_dash_density(t: str) -> list[Span]:
    exempt = {m.end() - 1 for m in _LIST_LABEL_DASH.finditer(t)}
    dashes = [m.span() for m in re.finditer(r"—|–|(?<=\w) -- (?=\w)|(?<=\w) - (?=\w)", t)
              if m.start() not in exempt and not _between_digits(t, *m.span())]
    words = max(1, len(re.findall(r"\b\w+\b", t)))
    allowed = max(1, int(words / 100))  # one dash per 100 words is fine
    return dashes[allowed:] if len(dashes) > allowed else []


DETECTORS: dict[str, Callable[[str], list[Span]]] = {
    "triad_fragments": det_triad_fragments,
    "triad_list": det_triad_list,
    "adjective_pile": det_adjective_pile,
    "em_dash_density": det_em_dash_density,
}


@dataclass(frozen=True)
class Found:
    rule: Rule
    start: int
    end: int
    keep: Span | None = None


def _detect(text: str, rules: Iterable[Rule]) -> list[Found]:
    view = _fold_apostrophes(mask(text))
    found: list[Found] = []
    for r in rules:
        cands: list[tuple[int, int, Span | None]] = []
        if r.detector:
            cands += [(s, e, None) for s, e in DETECTORS[r.detector](view)]
        for p in r.patterns:
            for m in p.finditer(view):
                keep = m.span("keep") if "keep" in p.groupindex and m.group("keep") is not None else None
                cands.append((m.start(), m.end(), keep))
        taken: list[Span] = []
        for s, e, keep in sorted(cands, key=lambda c: c[:2]):
            while s < e and text[s].isspace():
                s += 1
            while e > s and text[e - 1].isspace():
                e -= 1
            if s == e or any(s < e2 and e > s2 for s2, e2 in taken):
                continue
            taken.append((s, e))
            found.append(Found(r, s, e, keep))
    return sorted(found, key=lambda f: (f.start, f.rule.id))


_INDENT = r"[ \t]*"
_MARKER = r"(?:[-*+>]|\d+[.)]|#{1,6})[ \t]+"
_PREFIX = re.compile(_INDENT + "(?:" + _MARKER + ")?")
_SENTENCE = re.compile(r"\S.*?(?:[.!?]+[\"')\]”’]*(?=\s|$)|$)")
_DASH = re.compile(r"[ \t]*[—–][ \t]*|(?<=\w) -- (?=\w)|(?<=\w) - (?=\w)")
_SPACED_DASH = re.compile(r"(?<=\S)[ \t]+(?:—|–|--?)[ \t]+(?=\S)")


def _sentences(text: str) -> list[Span]:
    out, pos = [], 0
    for line in mask(text, "x").split("\n"):
        body = _PREFIX.match(line).end()
        out += [(pos + m.start(), pos + m.end()) for m in _SENTENCE.finditer(line, body)]
        pos += len(line) + 1
    return out


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    text: str


Plan = tuple[Edit, ...]


class Rewriter(NamedTuple):
    plan: Callable[[str, Found], Plan]
    note: str


def _case_like(rep: str, orig: str) -> str:
    return rep[:1].upper() + rep[1:] if orig[:1].isupper() else rep


def _lower_first(s: str) -> str:
    head = s.split(" ", 1)[0]
    return s if head == "I" or (len(head) > 1 and head.isupper()) else s[:1].lower() + s[1:]


def _plan_delete(text: str, f: Found) -> Plan:
    keep = text[f.keep[0]:f.keep[1]] if f.keep else ""
    return (Edit(f.start, f.end, _case_like(keep, text[f.start:f.end])),)


def _plan_plain_word(text: str, f: Found) -> Plan:
    word = text[f.start:f.end]
    rep = PLAIN.get(word.lower())
    return () if rep is None else (Edit(f.start, f.end, _case_like(rep, word)),)


def _plan_dash_to_comma(text: str, f: Found) -> Plan:
    view = mask(text)
    a, b = next(((a, b) for a, b in _sentences(text) if a <= f.start < b), (f.start, f.end))
    return tuple(Edit(m.start(), m.end(), ", ") for m in _DASH.finditer(view, a, b)
                 if not _between_digits(view, m.start(), m.end()))


def _plan_join_fragments(text: str, f: Found) -> Plan:
    beats = re.findall(r"([^.!?]+)([.!?])", text[f.start:f.end])
    if len(beats) < 2:
        return ()
    words = [beats[0][0].strip()] + [_lower_first(b.strip()) for b, _ in beats[1:]]
    return (Edit(f.start, f.end, ", ".join(words[:-1]) + ", and " + words[-1] + beats[-1][1]),)


def _plan_state_directly(text: str, f: Found) -> Plan:
    if not f.keep:
        return ()
    answer = text[f.keep[0]:f.keep[1]]
    if len(answer.split()) >= 3:
        return (Edit(f.start, f.end, answer),)
    question = text[f.start:f.keep[0]].rstrip().rstrip("?")
    return (Edit(f.start, f.end, f"{question} is {_lower_first(answer)}"),)


REWRITERS: dict[str, Rewriter] = {
    "delete": Rewriter(_plan_delete,
                       "Deletes the flagged words. When the pattern marks a part to keep, only that part stays."),
    "plain-word": Rewriter(_plan_plain_word,
                           "Swaps the word for a plain one, so leverage becomes use. A word with no plain entry is left for you."),
    "dash-to-comma": Rewriter(_plan_dash_to_comma, "Turns every dash in the sentence into a comma."),
    "join-fragments": Rewriter(_plan_join_fragments,
                               "Joins the fragments into one sentence, so Plan. Build. Ship. becomes Plan, build, and ship."),
    "state-directly": Rewriter(_plan_state_directly,
                               "Keeps the answer as the sentence. A short answer becomes The result is the answer."),
    "none": Rewriter(lambda text, f: (), "No automatic edit. The rewriter leaves this one for you."),
}
FLOOR_NOTE = "After any edit, a sentence left under 3 words or ending on a dangling word is removed."

PLAIN = {
    "leverage": "use", "leverages": "uses", "leveraged": "used", "leveraging": "using",
    "seamless": "", "seamlessly": "", "robust": "solid", "delve": "look", "delves": "looks",
    "delving": "looking", "supercharge": "speed up", "supercharges": "speeds up",
    "game-changing": "", "game changer": "big change", "game-changer": "big change",
    "cutting-edge": "new", "cutting edge": "new", "next-level": "better", "unleash": "use",
    "revolutionize": "change", "unlock the": "get the", "unlock your": "get your",
    "elevate your": "improve your", "landscape of": "world of", "realm of": "world of", "revolutionizes": "changes", "ever-evolving": "changing",
}


def _plan(text: str, f: Found) -> Plan:
    plan = REWRITERS[f.rule.rewriter].plan(text, f)
    return () if any("\n" in text[e.start:e.end] for e in plan) else plan


_DANGLING = {"a", "an", "the", "is", "are", "was", "were", "of", "to", "and", "or", "but", "with", "for", "your", "my"}


class _SentenceRepair(NamedTuple):
    text: str
    kept: bool


def _below_floor(s: str) -> bool:
    words = [w for w in s.split() if re.search(r"\w", w)]
    if not words or len(words) < 3 or not re.search(r"[^\W\d_]", s):
        return True
    return re.sub(r"\W", "", words[-1]).lower() in _DANGLING


def _fix_articles(s: str, junctions: list[int]) -> str:
    for j in sorted(junctions, reverse=True):
        art = re.search(r"\b([Aa]n?)[ \t]+$", s[:j])
        nxt = re.match(r"[ \t]*([A-Za-z])", s[j:])
        if art and nxt:
            want = "an" if nxt.group(1).lower() in "aeiou" else "a"
            if art.group(1).lower() != want:
                s = s[:art.start(1)] + _case_like(want, art.group(1)) + s[art.end(1):]
    return s


def _repair_sentence(s: str) -> _SentenceRepair:
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"[ \t]+(?=[,.;:!?])", "", s)
    s = _SPACED_DASH.sub(lambda m: m.group() if _between_digits(s, m.start(), m.end()) else ", ", s)
    s = re.sub(r"([,;:])(?:[ \t]*[,;:])+", r"\1", s)
    s = re.sub(r"[,;:][ \t]*(?=[.!?])", "", s)
    s = re.sub(r"(?<!\.)\.\.(?!\.)", ".", s)
    s = re.sub(r"^[\s,;:—–-]+", "", s)
    s = re.sub(r"[\s,;:—–-]+(?=[.!?]*$)", "", s)
    s = re.sub(r"\b(an?|the),", r"\1", s, flags=re.I)
    m = re.match(r"(?:and|but|or)\s+(.*)", s, re.I | re.S)
    if m and len(m.group(1).split()) >= 3:
        s = m.group(1)
    s = re.sub(r"^([\"'(\[“‘]*)([a-z])", lambda m: m.group(1) + m.group(2).upper(), s)
    return _SentenceRepair(s, not _below_floor(s))


@dataclass(frozen=True)
class Outcome:
    kind: Literal["replaced", "deleted", "dropped", "covered", "untouched"]
    detail: str = ""

    def suggestion(self) -> str:
        return {"replaced": self.detail, "deleted": "(delete)", "dropped": "(removes the sentence)",
                "covered": f"(handled by {self.detail})", "untouched": "(no automatic edit)"}[self.kind]


def _units(edits: list[Edit], sents: list[Span]) -> list[tuple[int, int, list[Edit]]]:
    spans = []
    for e in edits:
        touched = [s for s in sents if s[0] < e.end and e.start < s[1]]
        spans.append((min([e.start] + [a for a, _ in touched]), max([e.end] + [b for _, b in touched])))
    merged: list[Span] = []
    for a, b in sorted(spans):
        if merged and a < merged[-1][1]:
            merged[-1] = (merged[-1][0], max(b, merged[-1][1]))
        else:
            merged.append((a, b))
    return [(a, b, [e for e in edits if a <= e.start and e.end <= b]) for a, b in merged]


def _probe_removed(offset: int, ends: list[tuple[int, bool]]) -> bool:
    return not next((kept for end, kept in ends if end >= offset), False)


def _repair_unit(text: str, start: int, end: int, edits: list[Edit], probes: set[int]) -> tuple[str, set[int]]:
    def shift(p: int) -> int:
        return p - start + sum(len(e.text) - (e.end - e.start) for e in edits if e.end <= p)

    body = text[start:end]
    for e in sorted(edits, key=lambda e: -e.start):
        body = body[:e.start - start] + e.text + body[e.end - start:]
    junctions = [shift(e.start) for e in edits]
    kept, ends = [], []
    for m in _SENTENCE.finditer(mask(body, "x")):
        a, b = m.span()
        fixed = _repair_sentence(_fix_articles(body[a:b], [j - a for j in junctions if a <= j <= b]))
        ends.append((b, fixed.kept))
        if fixed.kept:
            kept.append(fixed.text)
    gone = {p for p in probes if start <= p < end and _probe_removed(shift(p), ends)}
    return " ".join(kept), gone


def _land(found: list[Found], plans: list[Plan]) -> tuple[list[bool], dict[Edit, str]]:
    def _longest_plan_first(i: int) -> tuple[int, int, str]:
        plan = plans[i]
        start = min(e.start for e in plan)
        end = max(e.end for e in plan)
        return (start - end, start, found[i].rule.id)

    landed, owner = [False] * len(found), {}
    for i in sorted((i for i, p in enumerate(plans) if p), key=_longest_plan_first):
        if all(e in owner for e in plans[i]):
            landed[i] = True
        elif not any(e.start < o.end and o.start < e.end for e in plans[i] for o in owner):
            landed[i] = True
            owner.update({e: found[i].rule.id for e in plans[i]})
    return landed, owner


def _rewrite(text: str, found: list[Found]) -> tuple[str, list[Outcome]]:
    plans = [_plan(text, f) for f in found]
    landed, owner = _land(found, plans)
    if not owner:
        return text, [Outcome("untouched")] * len(found)

    edits = sorted(owner, key=lambda e: e.start)
    units = _units(edits, _sentences(text))
    probes = {e.start for e in edits} | {f.start for f, ok in zip(found, landed) if not ok}
    rows: list[str | None] = []
    gone: set[int] = set()
    pos = 0
    lines = text.split("\n")
    if text.endswith("\n"):
        lines.pop()
    for line in lines:
        lo, hi = pos, pos + len(line)
        pos = hi + 1
        mine = [u for u in units if lo <= u[0] < hi]
        if not mine:
            rows.append(line)
            continue
        plen = _PREFIX.match(line).end()
        buf, cur = "", lo
        for a, b, unit_edits in mine:
            new, removed = _repair_unit(text, a, b, unit_edits, probes)
            gone |= removed
            head = buf + text[cur:a]
            cur = b
            if new:
                buf = head + new
            elif head[plen:].strip():
                buf = head.rstrip(" \t")
            else:
                buf = head
                cur += len(re.match(r"[ \t]*", text[b:hi]).group())
        buf += text[cur:hi]
        rows.append(buf if buf[plen:].strip() else None)

    out: list[str] = []
    seam = False
    for row in rows:
        if row is None:
            seam = True
            continue
        if seam and not row.strip() and (not out or not out[-1].strip()):
            seam = False
            continue
        seam = False
        out.append(row)
    if seam and out and not out[-1].strip():
        out.pop()
    result = "\n".join(out) + ("\n" if out and text.endswith("\n") else "")

    outcomes = []
    for f, plan, ok in zip(found, plans, landed):
        if ok:
            e = next((e for e in plan if e.start <= f.start < e.end), plan[0])
            outcomes.append(Outcome("dropped") if e.start in gone else
                            Outcome("replaced", e.text.strip()) if e.text.strip() else Outcome("deleted"))
            continue
        cover = next((e for e in owner if e.start <= f.start and f.end <= e.end), None)
        outcomes.append(Outcome("covered", owner[cover]) if cover else
                        Outcome("dropped") if f.start in gone else Outcome("untouched"))
    return result, outcomes


# ---------------------------------------------------------------- check
def _line_col(text: str, idx: int) -> tuple[int, int]:
    line = text.count("\n", 0, idx) + 1
    col = idx - (text.rfind("\n", 0, idx) + 1) + 1
    return line, col


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'’]+\b", mask(text)))


def score_hits(hits: list[Hit], rules: Iterable[Rule], words: int) -> tuple[int, dict, dict]:
    by_rule: dict[str, int] = {}
    for h in hits:
        by_rule[h.rule] = by_rule.get(h.rule, 0) + 1
    scale = max(1.0, words / 200.0)  # long docs: judge density, not raw count
    pen: dict[str, float] = {}
    for r in rules:
        n = by_rule.get(r.id, 0)
        if n:
            pen[r.id] = round(min(r.cap, r.weight * n / scale), 2)
    return max(0, min(100, round(100 - sum(pen.values())))), by_rule, pen


def verdict_for(score: int) -> str:
    return "pass" if score >= PASS_AT else "warn" if score >= WARN_AT else "fail"


def check(text: str, rules: list[Rule] | None = None, *, llm: bool = False) -> Report:
    rules = rules if rules is not None else load_rules()
    found = _detect(text, rules)
    rewritten, outcomes = _rewrite(text, found)
    hits = [Hit(f.rule.id, f.rule.name, f.start, f.end, text[f.start:f.end], f.rule.why, f.rule.fix,
                o.suggestion(), *_line_col(text, f.start)) for f, o in zip(found, outcomes)]
    words = word_count(text)
    score, by_rule, pen = score_hits(hits, rules, words)
    rep = Report(score, verdict_for(score), words, hits, by_rule, pen, rewritten)
    if llm:
        from .llm import llm_pass
        rep.llm = llm_pass(text, rep)
    return rep
