"""Give DRISHTI accounts one-time passwords through the Keycloak admin API.

The realm file (deploy/keycloak/drishti-realm.json) ships no passwords: every account must change its
password and enrol an authenticator app (TOTP) at first sign-in. This script sets a random one-time
password for each named account and writes it to a file readable only by the person running it, to be
handed to the officer through a separate channel.

    python scripts/keycloak_users.py --url http://localhost:8081 --admin kcadmin --admin-password-file var/secrets/kc_admin_password \
        --out var/secrets/one_time_passwords.json io.pune sp.pune auditor.oversight

--reimport deletes the realm and imports deploy/keycloak/drishti-realm.json again (test servers only).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import string
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _request(method: str, url: str, token: str | None = None, body: object | None = None, form: dict | None = None) -> object:
    data, headers = None, {}
    if form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def one_time_password() -> str:
    """Meets the realm policy: 12+ characters with a digit, an upper-case letter and a special character."""
    core = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(18))
    return f"{secrets.choice(string.ascii_uppercase)}{secrets.choice(string.digits)}{secrets.choice('!#%+-=@')}{core}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("users", nargs="*")
    ap.add_argument("--url", default="http://localhost:8081")
    ap.add_argument("--realm", default="drishti")
    ap.add_argument("--admin", default="kcadmin")
    ap.add_argument("--admin-password-file", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--reimport", action="store_true")
    args = ap.parse_args()
    admin_pw = args.admin_password_file.read_text(encoding="utf-8").strip()
    token = _request("POST", f"{args.url}/realms/master/protocol/openid-connect/token",
                     form={"grant_type": "password", "client_id": "admin-cli", "username": args.admin, "password": admin_pw})["access_token"]
    if args.reimport:
        try:
            _request("DELETE", f"{args.url}/admin/realms/{args.realm}", token)
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
        realm = json.loads((ROOT / "deploy" / "keycloak" / "drishti-realm.json").read_text(encoding="utf-8"))
        _request("POST", f"{args.url}/admin/realms", token, body=realm)
        print(f"realm {args.realm} re-imported")
    issued = {}
    for username in args.users:
        found = _request("GET", f"{args.url}/admin/realms/{args.realm}/users?exact=true&username={urllib.parse.quote(username)}", token)
        if not found:
            raise SystemExit(f"no such user: {username}")
        pw = one_time_password()
        _request("PUT", f"{args.url}/admin/realms/{args.realm}/users/{found[0]['id']}/reset-password", token,
                 body={"type": "password", "value": pw, "temporary": True})
        issued[username] = pw
    if issued:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(issued, indent=1), encoding="utf-8")
        try:
            os.chmod(args.out, 0o600)
        except OSError:
            pass
        print(f"one-time passwords for {', '.join(issued)} written to {args.out} (hand over separately; they expire at first sign-in)")


if __name__ == "__main__":
    main()
