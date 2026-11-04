"""Core: parse banned.md, detect tells, score, and rewrite. Stdlib only."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable, Iterable

DEFAULT_BANNED = Path(os.environ.get("TELLS_GATE_BANNED", Path(__file__).resolve().parent.parent / "banned.md"))
PASS_AT = 80
WARN_AT = 60


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
_FIELD = re.compile(r"^-\s+(why|fix|weight|cap|pattern|detector|example|case):\s?(.*)$")


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
        rules.append(Rule(cur["id"], cur["name"], cur.get("why", ""), cur.get("fix", ""),
                          float(cur.get("weight", 5)), float(cur.get("cap", 15)), pats,
                          cur.get("detector"), cur.get("example", "")))

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


def mask(text: str) -> str:
    """Blank out code, URLs and HTML with spaces so offsets stay valid."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    out = _CODE_FENCE.sub(blank, text)
    out = _INLINE.sub(blank, out)
    out = _HTML.sub(blank, out)
    # keep URLs visible to the arrow rule: mask only the URL body after the scheme
    out = _URL.sub(lambda m: m.group(0)[:8] + " " * (len(m.group(0)) - 8), out)
    return out


# ---------------------------------------------------------------- detectors
Span = tuple[int, int]
_SENT_END = re.compile(r"(?<=[.!?])\s+|\n+")
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
    "fast", "simple", "reliable", "secure", "smart", "faster", "smarter", "better", "cheaper",
    "easier", "stronger", "safer", "clean", "clear", "bold",
}


def det_triad_fragments(t: str) -> list[Span]:
    # three or more consecutive 1-2 word sentences: "Write. Edit. Ship."
    pat = re.compile(r"(?:(?<=^)|(?<=[\s>]))((?:[A-Z][\w'’-]*(?: [\w'’-]+)?[.!] ){2,}[A-Z][\w'’-]*(?: [\w'’-]+)?[.!])(?=\s|$)", re.M)
    return [m.span(1) for m in pat.finditer(t)]


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


def det_em_dash_density(t: str) -> list[Span]:
    # exempt numeric ranges (3–1, 8–10) and list labels ("- **Kickoff** — ...", "1. Kickoff — ...")
    label = re.compile(r"(?m)^\s*(?:[-*+]|\d+\.)\s+(?:\*\*[^*\n]{1,60}\*\*|`[^`\n]{1,60}`|\S[^—–\n]{0,40}?)\s*[—–]")
    exempt = {m.end() - 1 for m in label.finditer(t)}
    dashes = [m.span() for m in re.finditer(r"—|–|(?<=\w) -- (?=\w)|(?<=\w) - (?=\w)", t)
              if m.start() not in exempt and not re.match(r"\d[–—]\d", t[max(0, m.start() - 1):m.end() + 1])]
    words = max(1, len(re.findall(r"\b\w+\b", t)))
    allowed = max(1, int(words / 100))  # one dash per 100 words is fine
    return dashes[allowed:] if len(dashes) > allowed else []


DETECTORS: dict[str, Callable[[str], list[Span]]] = {
    "triad_fragments": det_triad_fragments,
    "triad_list": det_triad_list,
    "adjective_pile": det_adjective_pile,
    "em_dash_density": det_em_dash_density,
}


# ---------------------------------------------------------------- suggestions
def suggest(rule: Rule, frag: str) -> str:
    f = frag.strip()
    rid = rule.id
    if rid == "TG001":
        return _fix_not_x(f)
    if rid in ("TG002", "TG006", "TG013", "TG014", "TG017", "TG012"):
        return "(delete)"
    if rid == "TG007":
        return f.split(".")[0] + "."
    if rid in ("TG008", "TG009"):
        parts = [p for p in re.split(r",\s*(?:and\s+)?|\s+and\s+|\s*&\s*", f) if p]
        return parts[-1] if rid == "TG009" else parts[0]
    if rid == "TG010":
        return PLAIN.get(f.lower(), "(plain word)")
    if rid == "TG011":
        return "(delete)"
    if rid == "TG015":
        return ","
    if rid == "TG016":
        return "(state it directly)"
    return rule.fix


PLAIN = {
    "leverage": "use", "leverages": "uses", "leveraged": "used", "leveraging": "using",
    "seamless": "", "seamlessly": "", "robust": "solid", "delve": "look", "delves": "looks",
    "delving": "looking", "supercharge": "speed up", "supercharges": "speeds up",
    "game-changing": "", "game changer": "big change", "game-changer": "big change",
    "cutting-edge": "new", "cutting edge": "new", "next-level": "better", "unleash": "use",
    "revolutionize": "change", "unlock the": "get the", "unlock your": "get your",
    "elevate your": "improve your", "landscape of": "world of", "realm of": "world of", "revolutionizes": "changes", "ever-evolving": "changing",
}


# ---------------------------------------------------------------- check
def _line_col(text: str, idx: int) -> tuple[int, int]:
    line = text.count("\n", 0, idx) + 1
    col = idx - (text.rfind("\n", 0, idx) + 1) + 1
    return line, col


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w'’]+\b", mask(text)))


def find_hits(text: str, rules: Iterable[Rule]) -> list[Hit]:
    t = mask(text)
    hits: list[Hit] = []
    for r in rules:
        spans: list[Span] = []
        if r.detector:
            spans += DETECTORS[r.detector](t)
        for p in r.patterns:
            spans += [m.span() for m in p.finditer(t) if m.end() > m.start()]
        seen: list[Span] = []
        for s, e in sorted(set(spans)):
            if any(s < e2 and e > s2 for s2, e2 in seen):
                continue  # de-dupe overlaps within a rule
            seen.append((s, e))
            frag = text[s:e]
            ln, col = _line_col(text, s)
            hits.append(Hit(r.id, r.name, s, e, frag, r.why, r.fix, suggest(r, frag), ln, col))
    hits.sort(key=lambda h: (h.start, h.rule))
    return hits


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


def check(text: str, rules: list[Rule] | None = None, *, llm: bool = False, with_rewrite: bool = True) -> Report:
    rules = rules if rules is not None else load_rules()
    hits = find_hits(text, rules)
    words = word_count(text)
    score, by_rule, pen = score_hits(hits, rules, words)
    rep = Report(score, verdict_for(score), words, hits, by_rule, pen)
    if with_rewrite:
        rep.rewrite = rewrite(text, rules, hits)
    if llm:
        from .llm import llm_pass
        rep.llm = llm_pass(text, rep)
    return rep


# ---------------------------------------------------------------- rewrite
def _fix_not_x(frag: str) -> str:
    m = re.search(r"^(.*?)\bnot (?:just |only |merely )?(?:a |an |about )?[^.,;!?\n]{1,40},? but (?:rather )?(.*)$", frag, re.I | re.S)
    if m:
        return (m.group(1) + m.group(2)).strip()
    m = re.search(r"^(\w+)(?:'s| is|n't)?.*?[,;—–.-]\s*(?:it|this|that)(?:'s| is)\s*(.*)$", frag, re.I | re.S)
    if m:
        subj = m.group(1)
        subj = subj if subj.lower() in ("it", "this", "that") else "It"
        return (f"{subj}'s " if subj.lower() == "it" else f"{subj} is ") + m.group(2).strip() if m.group(2) else frag
    return frag


def rewrite(text: str, rules: list[Rule] | None = None, hits: list[Hit] | None = None) -> str:
    """Deterministic cleanup. Applies edits right-to-left so offsets stay valid."""
    rules = rules if rules is not None else load_rules()
    hits = hits if hits is not None else find_hits(text, rules)
    edits: list[tuple[int, int, str]] = []
    taken: list[Span] = []
    order = {"TG006": 0, "TG013": 0, "TG014": 0, "TG017": 0, "TG001": 1}
    for h in sorted(hits, key=lambda h: (order.get(h.rule, 5), h.start)):
        s, e = h.start, h.end
        rep: str | None = None
        if h.rule in ("TG006", "TG014", "TG013", "TG017", "TG012", "TG003", "TG004"):
            # drop the whole sentence/clause the tell lives in when it is short
            ss = max(text.rfind(c, 0, s) for c in ".!?\n") + 1
            m = re.search(r"[.!?]|(?=\n)", text[e:])
            ee = e + (m.end() if m else len(text) - e)
            sentence = text[ss:ee]
            if h.rule in ("TG003", "TG004") and len(sentence.split()) > 12:
                continue
            if h.rule == "TG012" or len(sentence.split()) > 12:
                rep, ee, ss = "", e, s
                # also eat a following comma/space
                mm = re.match(r",?\s*", text[ee:])
                ee += mm.end() if mm else 0
            s, e, rep = ss, ee, (rep if rep is not None else "")
        elif h.rule == "TG002":
            mm = re.match(r"\s*", text[e:])
            e += mm.end() if mm else 0
            rep = ""
        elif h.rule == "TG011":
            mm = re.match(r":?[ \t]*", text[e:])
            e += mm.end() if mm else 0
            rep = ""
        elif h.rule == "TG005":
            m = re.match(r"(.*?)\s+like an?\b", h.text, re.I)
            rep = m.group(1) if m else h.text
            mm = re.match(r"(?:[ \w-]*?analyst|[ \w-]*?engineer|[ \w-]*?consultant|[ \w-]*?designer|[ \w-]*?lawyer|[ \w-]*?developer|[ \w-]*?pro|[ \w-]*?expert)\b", text[e:])
            e += mm.end() if mm else 0
        elif h.rule == "TG015":
            rep = ", " if text[s - 1:s] != " " else ", "
            # normalise surrounding spaces
            while s > 0 and text[s - 1] == " ":
                s -= 1
            while e < len(text) and text[e] == " ":
                e += 1
        elif h.rule == "TG010":
            w = h.text.lower()
            if w in PLAIN:
                rep = PLAIN[w]
                if rep == "":
                    mm = re.match(r",?\s*", text[e:])
                    e += mm.end() if mm else 0
            else:
                continue
        elif h.rule == "TG001":
            rep = _fix_not_x(h.text)
        elif h.rule == "TG009":
            mm = re.match(r"[ \t]*", text[e:])
            e += mm.end() if mm else 0
            rep = ""
        elif h.rule == "TG007":
            rep = h.suggestion
        elif h.rule == "TG016":
            m = re.match(r"(.*?)\?\s+(.*)$", h.text, re.S)
            rep = m.group(2) if m else h.text
        else:
            continue
        if any(s < e2 and e > s2 for s2, e2 in taken):
            continue
        taken.append((s, e))
        edits.append((s, e, rep))
    if not edits:
        return text
    out = text
    for s, e, rep in sorted(edits, key=lambda x: -x[0]):
        out = out[:s] + rep + out[e:]
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r" +([,.!?])", r"\1", out)
    out = re.sub(r",\s*,", ",", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"(?m)^[ \t]+|[ \t]+$", "", out)
    out = re.sub(r"(^|[.!?]\s+)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out.strip())
    return out
