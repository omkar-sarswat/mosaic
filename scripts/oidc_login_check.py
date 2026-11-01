"""End-to-end sign-in check against a real OIDC provider (Keycloak), with a headless browser.

    python scripts/oidc_login_check.py http://localhost:5173 io.pune <password> [new-password]

Opens the app, follows the redirect to the provider, signs in (changing a temporary password if asked),
returns to the app, checks that API calls carry a bearer token and succeed, that no token is stored in
localStorage or sessionStorage, and that signing out ends the session. Prints a JSON report.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import struct
import sys
import time

from playwright.sync_api import sync_playwright


def totp(secret_b32: str, at: float | None = None, step: int = 30, digits: int = 6) -> str:
    """RFC 6238 time-based one-time password (what an authenticator app shows)."""
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    counter = int((at or time.time()) // step)
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** digits
    return str(code).zfill(digits)


def main(base: str, username: str, password: str, new_password: str | None, otp_secret: str | None = None) -> dict:
    report: dict = {"steps": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        api_calls: list[tuple[int, str, bool]] = []
        page.on("response", lambda r: api_calls.append((r.status, r.url, bool(r.request.headers.get("authorization"))))
                if "/api/" in r.url and "/api/auth/config" not in r.url else None)
        page.goto(base + "/")
        page.wait_for_url("**/realms/**", timeout=20000)
        report["steps"].append(f"redirected to provider: {page.url.split('?')[0]}")
        page.fill("#username", username)
        page.fill("#password", password)
        page.click("#kc-login")
        # first sign-in: required actions (new password, authenticator app) in whatever order the provider asks
        for _ in range(4):
            page.wait_for_load_state("networkidle")
            if page.url.startswith(base):
                break
            if page.locator("#password-new").count():
                page.fill("#password-new", new_password or password + "-2026!")
                page.fill("#password-confirm", new_password or password + "-2026!")
                page.locator("input[type=submit], button[type=submit]").first.click()
                report["steps"].append("one-time password replaced")
            elif page.locator("#totp").count():
                if page.locator("#mode-manual").count():
                    page.click("#mode-manual")
                secret = page.locator("#kc-totp-secret-key").inner_text().replace(" ", "")
                report["totp_secret"] = secret
                page.fill("#totp", totp(secret))
                if page.locator("#userLabel").count():
                    page.fill("#userLabel", "headless check")
                page.locator("#saveTOTPBtn, input[type=submit], button[type=submit]").first.click()
                report["steps"].append("authenticator app enrolled (TOTP)")
            elif page.locator("#otp").count():
                # a code may be used once; if this window's code was spent (e.g. at enrolment), wait for the next
                if report.get("otp_attempts"):
                    page.wait_for_timeout((30 - time.time() % 30 + 1) * 1000)
                report["otp_attempts"] = report.get("otp_attempts", 0) + 1
                page.fill("#otp", totp(otp_secret or ""))
                page.click("#kc-login")
                report["steps"].append("one-time code entered")
        page.wait_for_url(base + "/**", timeout=20000)
        page.wait_for_selector("[title^='Signed in as']", timeout=20000)
        report["signed_in_as"] = page.locator("[title^='Signed in as']").first.get_attribute("title")
        report["url_after_callback"] = page.url
        storage = page.evaluate("() => JSON.stringify({local: {...localStorage}, session: {...sessionStorage}})")
        report["token_in_browser_storage"] = any(k in storage for k in ("access_token", "refresh_token", "eyJ"))
        page.wait_for_timeout(2000)
        report["api_calls"] = len(api_calls)
        report["api_calls_with_bearer"] = sum(1 for _, _, b in api_calls if b)
        report["api_errors"] = [(s, u) for s, u, _ in api_calls if s >= 400]
        page.locator("[title^='Signed in as']").first.click()
        page.wait_for_load_state("networkidle")
        page.goto(base + "/")
        page.wait_for_url("**/realms/**", timeout=20000)
        report["after_sign_out"] = "provider login page shown again" if page.locator("#username").count() else page.url
        browser.close()
    return report


if __name__ == "__main__":
    args = sys.argv[1:]
    print(json.dumps(main(args[0], args[1], args[2], args[3] if len(args) > 3 else None, args[4] if len(args) > 4 else None), indent=1))
