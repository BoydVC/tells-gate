# Integrating Tells Gate with X Post Queue (:4340)

Not applied. The running X Post Queue (`/workspace/tokenmax/x-post-queue/server.py`) is untouched.
This is the exact patch to make **Approve** call Tells Gate first. It fails open (if Tells Gate is
down, approve still works and the item gets a note), so the queue never gets stuck.

Run Tells Gate: `./tells-gate serve --port 4350`

## Patch (server.py)

```diff
--- a/server.py
+++ b/server.py
@@ imports
 import json
 import os
 import re
 import threading
+import urllib.request
 import uuid
@@ after STATUSES = (...)
+TELLS_GATE_URL = os.environ.get("TELLS_GATE_URL", "http://127.0.0.1:4350/check")
+TELLS_GATE_MIN = int(os.environ.get("TELLS_GATE_MIN", "80"))
+
+
+def tells_gate(text: str) -> dict | None:
+    """POST the draft to Tells Gate. Returns its report, or None if unreachable (fail open)."""
+    body = json.dumps({"text": text, "min_score": TELLS_GATE_MIN}).encode()
+    req = urllib.request.Request(TELLS_GATE_URL, body, {"Content-Type": "application/json"})
+    try:
+        with urllib.request.urlopen(req, timeout=3) as r:
+            return json.load(r)
+    except Exception:
+        return None
@@ in do_POST, action handler
             if action == "approve":
                 if it["status"] not in ("draft", "approved"):
                     return self._json(400, {"error": f"cannot approve from status={it['status']}"})
+                force = (self._read_json() or {}).get("force") is True
+                gate = tells_gate(it["text"])
+                if gate is None:
+                    it["notes"] = ((it.get("notes") or "") + " [tells-gate unreachable; approved unchecked]").strip()
+                else:
+                    it["tells_score"] = gate["score"]
+                    it["tells_hits"] = [f'{h["rule"]}:{h["text"].strip()[:40]}' for h in gate["hits"]]
+                    if gate["gate"] == "block" and not force:
+                        save_queue(q)
+                        return self._json(409, {"error": "tells-gate blocked", "score": gate["score"],
+                                                "hits": gate["hits"], "rewrite": gate["rewrite"],
+                                                "hint": "edit the draft, or POST {\"force\": true} to approve anyway"})
                 it["status"] = "approved"
```

UI (optional, in the approve click handler): on a 409, show `score`, the hit list and a
"Use rewrite" button that PUTs `rewrite` into the item's text, plus an "Approve anyway" button
that re-POSTs with `{"force": true}`. The human still taps Post on X; nothing auto-posts.

## Contract

`POST /check` with `{"text": str, "min_score"?: int, "llm"?: bool}` returns
`{score, verdict, words, hits[{rule,name,start,end,text,why,fix,suggestion,line,col}], by_rule, penalties, rewrite, llm, gate}`.
`gate` is `block` when `score < min_score` (or verdict `fail`, <60, if no min_score). Offsets are Unicode code points.
Each hit's `suggestion` is what `rewrite` did to that hit.

## Smoke test after applying

```bash
curl -s -XPOST localhost:4350/check -H 'Content-Type: application/json' \
  -d '{"text":"🚨 It quietly shipped. That'\''s the whole game.","min_score":80}' | python3 -m json.tool | head
```
