"""Optional LLM pass. Stubbed: deterministic rules are the gate.

Enable with --llm / {"llm": true}. With TELLS_GATE_LLM_URL unset this returns a
stub result and never makes a network call, so tests and CI stay offline.
A real backend should POST {"text", "hits"} and return {"notes": [...], "rewrite": str}.
"""
from __future__ import annotations

import json
import os
import urllib.request


def llm_pass(text: str, report) -> dict:
    url = os.environ.get("TELLS_GATE_LLM_URL")
    if not url:
        return {"enabled": False, "status": "stub", "notes": [],
                "message": "LLM pass is stubbed; set TELLS_GATE_LLM_URL to enable."}
    body = json.dumps({"text": text, "hits": [h.rule for h in report.hits]}).encode()
    req = urllib.request.Request(url, body, {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:  # pragma: no cover
        data = json.load(r)
    return {"enabled": True, "status": "ok", **data}
