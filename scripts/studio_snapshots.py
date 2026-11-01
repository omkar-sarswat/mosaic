"""Screenshot the data studio: each source, each tab, as an investigator in a case. Read-only.

    python scripts/studio_snapshots.py [base_url] [out_dir]
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "var" / "ui-review" / "studio")
OUT.mkdir(parents=True, exist_ok=True)


def api(path: str, user: str):
    with urllib.request.urlopen(urllib.request.Request(BASE + path, headers={"X-DRISHTI-User": user})) as r:
        return json.load(r)


case = next(c["id"] for c in api("/api/me", "crime.pi")["cases"] if "syndicate" in (c.get("title") or "").lower())
PLAN = [("kyc", "Bank KYC extract", ["Profile", "Recipe", "Mapping", "Matching", "Lenses", "Changes"]),
        ("hotel", "Hotel guest registers", ["Lenses", "Matching"]),
        ("rto", "RTO vehicle register extract", ["Lenses"]),
        ("notes", "Seized diary pages", ["Tagging", "Lenses"])]

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    errors: list[str] = []
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append("console: " + m.text) if m.type == "error" else None)
    page.goto(f"{BASE}/?user=crime.pi&view=studio&case={case}")
    page.wait_for_timeout(2500)
    page.screenshot(path=str(OUT / "00-studio.png"))
    for src, title, tabs in PLAN:
        page.get_by_text(title, exact=True).first.click()
        page.wait_for_timeout(2500)
        for t in tabs:
            page.get_by_role("tab", name=t).first.click()
            page.wait_for_timeout(1800 if t == "Lenses" else 800)
            page.screenshot(path=str(OUT / f"{src}-{t.lower()}.png"), full_page=False)
    ctx.close()
    browser.close()
print(json.dumps({"case": case, "errors": errors[:10]}, indent=1))
