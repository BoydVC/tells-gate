"""Behavior tests. Synthetic text only."""
import json
import re
import subprocess
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tells_gate import check, load_rules  # noqa: E402
from tells_gate.core import parse_banned, mask, REWRITERS  # noqa: E402
from tells_gate.server import make_handler  # noqa: E402

RULES = load_rules()
SAMPLES = ROOT / "tests/samples"


def ids(text):
    return {h.rule for h in check(text, RULES).hits}


def rewritten(text):
    return check(text, RULES).rewrite


class TestBanned(unittest.TestCase):
    def test_loads_all_rules_with_why_and_fix(self):
        self.assertGreaterEqual(len(RULES), 15)
        for r in RULES:
            self.assertRegex(r.id, r"^TG\d{3}$")
            self.assertTrue(r.why and r.fix and r.example, r.id)

    def test_every_rule_catches_its_own_example(self):
        for r in RULES:
            with self.subTest(rule=r.id):
                self.assertIn(r.id, ids(r.example), r.example)

    def test_parse_rejects_rule_without_pattern(self):
        with self.assertRaises(ValueError):
            parse_banned("## TG999 empty\n- why: x\n- fix: y\n")

    def test_parse_rejects_unknown_detector(self):
        with self.assertRaises(ValueError):
            parse_banned("## TG999 x\n- detector: nope\n")

    def test_parse_rejects_duplicate_ids(self):
        md = "## TG001 a\n- pattern: a\n## TG001 b\n- pattern: b\n"
        with self.assertRaises(ValueError):
            parse_banned(md)

    def test_parse_rejects_unknown_rewriter(self):
        with self.assertRaises(ValueError):
            parse_banned("## TG999 x\n- pattern: x\n- rewriter: nope\n")

    def test_every_rule_names_a_registered_rewriter(self):
        self.assertEqual(len(RULES), 17)
        for r in RULES:
            with self.subTest(rule=r.id):
                self.assertIn(r.rewriter, REWRITERS)

    def test_every_rule_has_bad_fixtures(self):
        self.assertEqual(set(BAD), {r.id for r in RULES})

    def test_custom_banned_file_is_honored(self):
        rules = parse_banned("## TG900 synergy\n- why: w\n- fix: f\n- weight: 50\n- cap: 50\n- pattern: \\bwidget\\b\n")
        rep = check("The widget is ready.", rules)
        self.assertEqual(rep.score, 50)
        self.assertEqual(rep.hits[0].rule, "TG900")


BAD = {
    "TG001": ["It's not a chatbot, it's a coworker.", "This is not about speed, it's about trust.",
              "We built not a tool but a teammate.", "That isn't just a feature. It's a platform."],
    "TG002": ["Apple quietly released an update."],
    "TG003": ["Set this up before Monday.", "Try it this weekend.", "Don't wait."],
    "TG004": ["Most people use ChatGPT wrong.", "You're probably using it wrong.", "99% of developers miss this."],
    "TG005": ["It can now code like a senior engineer.", "Grok can now research like a $200/hour analyst."],
    "TG006": ["That's the whole game.", "Let that sink in.", "Read that again.", "And that changes everything."],
    "TG007": ["Plan. Build. Ship.", "Dream big. Start small. Win."],
    "TG008": ["You get speed, clarity, and confidence."],
    "TG009": ["A powerful, seamless, intuitive app."],
    "TG010": ["We leverage AI to delve into data.", "A cutting-edge, next-level stack."],
    "TG011": ["🚨 New model out", "BREAKING: rates cut", "Full thread 🧵"],
    "TG012": ["It's worth noting that this is arguably faster."],
    "TG013": ["Let's dive in. Here's the plan.", "Here's the thing: it works."],
    "TG014": ["In conclusion, it works.", "Hope this helps!", "Follow for more."],
    "TG015": ["It works — fast — and it ships — today — for free."],
    "TG016": ["The result? Chaos.", "The catch? It costs money."],
    "TG017": ["Absolutely! Here is the answer."],
}

GOOD = [
    "I fixed the login bug on Tuesday. It took two hours.",
    "The Orioles traded a reliever for two prospects.",
    "We cut the build from 9 minutes to 4 by caching node_modules.",
    "My daughter finished her science fair poster tonight.",
    "Not bad for a first try.",
    "The meeting moved to 3 PM.",
    "Buy milk, eggs, and bread.",
    "Score was 3–1 at the half.",
    "It isn't raining.",
    "This is not ready yet.",
    "Rain is likely after 4 PM, so the game may move indoors.",
    "Quiet hours start at 10.",
]


class TestRules(unittest.TestCase):
    def test_bad_samples_flag_expected_rule(self):
        for rid, samples in BAD.items():
            for s in samples:
                with self.subTest(rule=rid, text=s):
                    self.assertIn(rid, ids(s))

    def test_good_samples_are_clean(self):
        for s in GOOD:
            with self.subTest(text=s):
                self.assertEqual(ids(s), set())

    def test_single_em_dash_in_short_post_is_fine(self):
        self.assertNotIn("TG015", ids("The fix shipped — finally."))

    def test_list_label_dashes_are_exempt(self):
        md = "1. **Kickoff** — countdown\n2. **Season** — week chips\n- **Matchup** — side by side\n"
        self.assertNotIn("TG015", ids(md))

    def test_code_blocks_and_urls_are_ignored(self):
        md = "Run it:\n\n```\nleverage --seamless --quietly\n```\nSee `robust` and https://x.com/quietly-delve\n"
        self.assertEqual(ids(md), set())

    def test_mask_preserves_length(self):
        t = "a `b` ```c``` https://d.e/f"
        self.assertEqual(len(mask(t)), len(t))

    def test_breaking_lowercase_is_not_siren(self):
        self.assertNotIn("TG011", ids("The ice is breaking up on the bay."))

    def test_spans_point_at_text(self):
        t = "Ok. Claude quietly shipped it."
        h = check(t, RULES).hits[0]
        self.assertEqual(t[h.start:h.end], "quietly")
        self.assertEqual((h.line, h.col), (1, 12))

    def test_line_col_multiline(self):
        h = check("one\ntwo quietly", RULES).hits[0]
        self.assertEqual((h.line, h.col), (2, 5))


class TestScore(unittest.TestCase):
    def test_clean_is_100_pass(self):
        r = check(GOOD[0], RULES)
        self.assertEqual((r.score, r.verdict), (100, "pass"))

    def test_sloppy_sample_fails(self):
        r = check((ROOT / "tests/samples/bad/hype-thread.md").read_text(), RULES)
        self.assertEqual(r.verdict, "fail")
        self.assertLess(r.score, 30)

    def test_good_files_pass(self):
        for f in (ROOT / "tests/samples/good").glob("*.md"):
            with self.subTest(f=f.name):
                r = check(f.read_text(), RULES)
                self.assertEqual((r.score, r.hits), (100, []))

    def test_bad_files_fail(self):
        for f in (ROOT / "tests/samples/bad").glob("*.md"):
            with self.subTest(f=f.name):
                self.assertEqual(check(f.read_text(), RULES).verdict, "fail")

    def test_cap_limits_one_rule(self):
        r = check("quietly " * 30, RULES)
        self.assertEqual(r.penalties["TG002"], 12)

    def test_long_docs_are_judged_by_density(self):
        filler = "We fixed the parser and wrote tests for it today. " * 80
        short = check("It quietly works.", RULES).score
        long = check(filler + "It quietly works.", RULES).score
        self.assertGreater(long, short)

    def test_score_bounds(self):
        r = check(" ".join(sum(BAD.values(), [])), RULES)
        self.assertTrue(0 <= r.score <= 100)

    def test_deterministic(self):
        t = (ROOT / "tests/samples/bad/linkedin-post.md").read_text()
        self.assertEqual(check(t, RULES).to_dict(), check(t, RULES).to_dict())

    def test_empty_text(self):
        r = check("", RULES)
        self.assertEqual((r.score, r.words, r.hits), (100, 0, []))


def sample_texts():
    return {f.name: f.read_text() for f in sorted(SAMPLES.glob("*/*.md"))}


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", text) if s.strip()]


ORPHAN = re.compile(r"^[,;:—–-]|[,;:—–-][.!?]*$|(?<!\.)\.\.(?!\.)|\b[Aa] [aeiou]|^\W+$|— and| -- and")


class TestRewrite(unittest.TestCase):
    def test_rewrite_lifts_bad_files(self):
        for f in (SAMPLES / "bad").glob("*.md"):
            t = f.read_text()
            with self.subTest(f=f.name):
                self.assertGreater(check(rewritten(t), RULES).score, check(t, RULES).score + 30)

    def test_clean_text_is_byte_identical(self):
        texts = GOOD + [f.read_text() for f in (SAMPLES / "good").glob("*.md")]
        texts += ["Keep.\n", "Run it:\n\n```\n  leverage --quietly\n```\n", "  indented\n"]
        for t in texts:
            with self.subTest(text=t[:40]):
                self.assertEqual(rewritten(t), t)

    def test_untouched_lines_keep_their_bytes(self):
        doc = "Title line\n\n  Indented note stays.  \n\nIt quietly shipped on Friday after the review.\n\n```\nx  =  1\n```\n"
        self.assertEqual(rewritten(doc), doc.replace("It quietly shipped", "It shipped"))

    def test_rewrite_specific_fixes(self):
        cases = {
            "Claude quietly shipped it.": "Claude shipped it.",
            "It's not a chatbot, it's a coworker.": "It's a coworker.",
            "We shipped it. That's the whole game.": "We shipped it.",
            "Plan. Build. Ship.": "Plan, build, and ship.",
            "Write. Edit. Ship.": "Write, edit, and ship.",
            "Dream big. Start small. Win.": "Dream big, start small, and win.",
            "The result? Pure magic.": "The result is pure magic.",
            "The catch? It costs money.": "It costs money.",
            "🚨 New model out": "New model out",
        }
        for before, after in cases.items():
            with self.subTest(text=before):
                self.assertEqual(rewritten(before), after)
        self.assertNotIn("leverage", rewritten("We leverage caching."))

    def test_rewrite_keeps_paragraphs(self):
        out = rewritten("The first line quietly.\n\nSecond line stays.")
        self.assertEqual(out, "The first line.\n\nSecond line stays.")

    def test_untouched_short_sentence_survives(self):
        self.assertEqual(rewritten("Ship it. It quietly works for the whole team today."),
                         "Ship it. It works for the whole team today.")

    def test_repair_fixes_the_junction(self):
        self.assertEqual(rewritten("We shipped a seamless app today."), "We shipped an app today.")
        self.assertEqual(rewritten("We built a seamless, fast app for the team."), "We built a fast app for the team.")
        self.assertEqual(rewritten("But it quietly works for the whole team."), "It works for the whole team.")

    def test_rewrites_read_as_sentences(self):
        for t in sum(BAD.values(), []) + [f.read_text() for f in (SAMPLES / "bad").glob("*.md")]:
            out = rewritten(t)
            with self.subTest(text=t[:50], rewrite=out):
                for s in sentences(out):
                    self.assertGreaterEqual(len(s.split()), 3, s)
                    self.assertIsNone(ORPHAN.search(s), s)

    def test_hype_rewrite_names_the_fixes(self):
        t = (SAMPLES / "bad/hype-thread.md").read_text()
        out = rewritten(t)
        for want in ("It's a coworker.", "The result is pure magic.", "Write, edit, and ship."):
            self.assertIn(want, out)
        for residue in ("It's a coworker. Write.", "Pure magic.", "— and", " -- and"):
            self.assertNotIn(residue, out)

    def test_rewrite_never_lowers_score(self):
        for t in sum(BAD.values(), []) + GOOD + list(sample_texts().values()):
            with self.subTest(text=t[:50]):
                self.assertGreaterEqual(check(rewritten(t), RULES).score, check(t, RULES).score)

    def test_suggestion_tells_the_truth(self):
        for t in sum(BAD.values(), []) + list(sample_texts().values()):
            rep = check(t, RULES)
            for h in rep.hits:
                with self.subTest(text=t[:50], rule=h.rule, suggestion=h.suggestion):
                    if h.suggestion in ("(delete)", "(removes the sentence)"):
                        self.assertNotIn(h.text, rep.rewrite)
                    elif h.suggestion == "(no automatic edit)":
                        self.assertIn(h.text, rep.rewrite)
                    elif not h.suggestion.startswith("(handled by "):
                        self.assertIn(h.suggestion, rep.rewrite)

    def test_llm_flag_is_stubbed_offline(self):
        r = check("hello", RULES, llm=True)
        self.assertEqual(r.llm["status"], "stub")


class TestCLI(unittest.TestCase):
    def run_cli(self, *args, stdin=None):
        return subprocess.run([str(ROOT / "tells-gate"), *args], input=stdin, capture_output=True, text=True)

    def test_check_json_and_exit_code(self):
        p = self.run_cli("check", "--json", str(ROOT / "tests/samples/bad/hype-thread.md"))
        self.assertEqual(p.returncode, 1)
        d = json.loads(p.stdout)
        self.assertEqual(d["verdict"], "fail")
        self.assertTrue(all({"rule", "start", "end", "suggestion"} <= set(h) for h in d["hits"]))

    def test_check_good_exits_zero(self):
        p = self.run_cli("check", str(ROOT / "tests/samples/good/plain-update.md"))
        self.assertEqual(p.returncode, 0)
        self.assertIn("100/100 PASS", p.stdout)

    def test_stdin_and_min_score(self):
        p = self.run_cli("check", "--min-score", "99", "-", stdin="It quietly works.")
        self.assertEqual(p.returncode, 1)

    def test_multiple_files_json_list(self):
        g = ROOT / "tests/samples/good"
        p = self.run_cli("check", "--json", *map(str, g.glob("*.md")))
        self.assertIsInstance(json.loads(p.stdout), list)

    def test_rules_listing(self):
        p = self.run_cli("rules")
        self.assertIn("TG001", p.stdout)


class TestHTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(RULES))
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()

    def post(self, body: bytes):
        req = urllib.request.Request(self.url + "/check", body, {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.load(r)
        except urllib.error.HTTPError as e:
            return e.code, json.load(e)

    def test_check_endpoint_blocks_sloppy(self):
        t = (ROOT / "tests/samples/bad/hype-thread.md").read_text()
        code, d = self.post(json.dumps({"text": t}).encode())
        self.assertEqual((code, d["gate"]), (200, "block"))

    def test_check_endpoint_allows_clean_and_min_score(self):
        code, d = self.post(json.dumps({"text": GOOD[0]}).encode())
        self.assertEqual(d["gate"], "allow")
        code, d = self.post(json.dumps({"text": "It quietly works.", "min_score": 99}).encode())
        self.assertEqual(d["gate"], "block")

    def test_bad_body_is_400(self):
        self.assertEqual(self.post(b"nope")[0], 400)
        self.assertEqual(self.post(b'{"text": 5}')[0], 400)

    def test_health_rules_and_page(self):
        with urllib.request.urlopen(self.url + "/health") as r:
            self.assertTrue(json.load(r)["ok"])
        with urllib.request.urlopen(self.url + "/rules") as r:
            self.assertEqual(len(json.load(r)), len(RULES))
        with urllib.request.urlopen(self.url + "/?text=hello") as r:
            self.assertIn(b"Tells Gate", r.read())


if __name__ == "__main__":
    unittest.main()
