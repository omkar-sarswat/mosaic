"""Screenshot every main screen as the role that uses it, and report page errors.

    python scripts/ui_snapshots.py [base_url] [out_dir]

Uses the installed Google Chrome through Playwright (no browser download). Read-only: it never
submits forms or approves anything.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "var" / "ui-review")
OUT.mkdir(parents=True, exist_ok=True)


def api(path: str, user: str, case: str | None = None):
    req = urllib.request.Request(BASE + path, headers={"X-DRISHTI-User": user, **({"X-DRISHTI-Case": case} if case else {})})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def case_for(user: str, word: str) -> str:
    return next(c["id"] for c in api("/api/me", user)["cases"] if word.lower() in (c.get("title") or "").lower())


mirage = case_for("ed.dd", "mirage")
syndicate = case_for("crime.pi", "syndicate")
leader = next(p["id"] for l in api("/api/patterns/leads?status=all", "crime.pi", syndicate)["leads"] if l["detector"] == "CONTINUING_UNLAWFUL_ACTIVITY"
              for p in l["parties"] if p["revealed"] and p["type"] == "Person")
kingpin = api("/api/intel/cases/" + mirage + "/board", "ed.dd", mirage)["suspects"][0]["id"]

SHOTS = [
    ("01-overview", "ed.dd", mirage, "home", None, 2500),
    ("02-network", "ed.dd", mirage, "graph", None, 3500),
    ("03-money", "ed.dd", mirage, "money", kingpin, 3500),
    ("04-leads-ncb", "ncb.io", None, "leads", None, 2500),
    ("05-dossier", "crime.pi", syndicate, "dossier", leader, 3000),
    ("06-cases", "ed.dd", mirage, "cases", None, 2500),
    ("07-alerts", "ed.dd", mirage, "alerts", None, 2000),
    ("08-connect", "crime.pi", syndicate, "connect", None, 2000),
    ("09-globe", "ed.dd", mirage, "globe", None, 4000),
    ("10-oversight", "auditor.oversight", None, "oversight", None, 2000),
]

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    report = {}
    for name, user, case, view, oid, wait in SHOTS:
        ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, device_scale_factor=1)
        page = ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
        page.on("console", lambda m, errors=errors: errors.append("console: " + m.text) if m.type == "error" else None)
        url = f"{BASE}/?user={user}&view={view}" + (f"&case={case}" if case else "") + (f"&id={oid}" if oid else "")
        page.goto(url)
        page.wait_for_timeout(wait)
        page.screenshot(path=str(OUT / f"{name}.png"))
        if view == "dossier":
            tab = page.get_by_role("tab", name="Record & patterns")
            if tab.count():
                tab.first.click()
                page.wait_for_timeout(1200)
                page.screenshot(path=str(OUT / f"{name}-record.png"))
        report[name] = errors[:5]
        ctx.close()
    browser.close()
print(json.dumps(report, indent=1))
