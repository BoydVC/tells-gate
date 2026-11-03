/poteto-mode /arena verifier for Tells Gate. Inputs: the 3 draft PRs (arena/types-first, arena/rules-first, arena/experience-first) and SPEC.md.
1. Check out each PR in a cloud sandbox and run the test suite. Record pass/fail, test count and runtime.
2. Score a shared held-out corpus (write it yourself, synthetic, 40 bad + 40 near-miss good lines, before reading the seats' corpora) with each seat's checker. Record per-rule precision/recall and the false positives on all public BoydVC READMEs (`gh api`, no clones).
3. Check the rewrite claims: it never lowers a score, leaves clean text byte-identical, and lifts the bad samples by more than 30 points. A seat that fails these fails, however good it looks.
4. Pick a base (best held-out F1 with zero README fails), then graft the best types from types-first and the best page and approve-gate UX from experience-first. Re-run everything.
5. Open ONE winner draft PR with a scorecard table, the demo.gif (synthetic, public raw URL) and INTEGRATION.md for X Post Queue. Do not merge, and do not patch the running X Post Queue. Leave the seat PRs open. Report to TokenMax.
