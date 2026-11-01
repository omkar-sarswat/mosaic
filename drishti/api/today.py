"""The signed-in person's day, as one list: what is due, what was decided, and the case on top.

One endpoint serves every role from the same database, through the same access rules as the screens it
points to: leads only from the agency's mission tracks (pseudonymous outside an open case), approvals
only for the person's agency and cases, matches only for roles that review them, the audit trail only
for oversight. Nothing here is a new permission; it gathers what each role could already open.

Entry marks (the interface draws each consistently):
  proposed   a machine proposal no person has confirmed (a lead, a match)
  pending    a request waiting for a second officer
  approved / rejected / dismissed   a human decision (drawn as a dated stamp)
  critical   an oversight alarm (canary record read, denied-access burst)
  flagged    a lesser oversight alarm (after-hours or bulk personal look-ups) for the auditor to inspect
  new        activity on a watched record or area, or new results for a saved search, not yet reviewed
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends

from ..guard import DEV_USERS
from ..guard.audit import AuditLog
from ..patterns import leads as L
from .deps import Ctx, get_ctx
from .watch import queue_entries

router = APIRouter(prefix="/api", tags=["today"])

SEVERITY = {"high": 0, "medium": 1, "low": 2}
LIMIT = 40


def _name(user_id: str | None) -> str | None:
    if not user_id:
        return None
    u = DEV_USERS.get(user_id)
    return u.name if u else user_id


def _short(ref: str) -> str:
    return ref.split(":", 1)[-1][:6].upper()


def _entry(at: str | None, kind: str, ref: str, title: str, detail: str, mark: str, view: str, target: str | None = None,
           by: str | None = None) -> dict[str, Any]:
    return {"at": at, "kind": kind, "ref": _short(ref), "id": ref, "title": title, "detail": detail, "mark": mark,
            "view": view, "target": target, "by": by, "by_name": _name(by)}


def _case_cover(c: Ctx) -> dict[str, Any] | None:
    case = c.case
    if not case or c.user.id not in case.members:
        return None
    s = c.svc.store
    row = s.query("SELECT * FROM cases WHERE id=?", (case.id,))
    if not row:
        return None
    meta = dict(row[0])
    subjects = []
    for r in s.query("SELECT co.object_id, co.reason, o.title, o.type FROM case_objects co JOIN objects o ON o.id=co.object_id "
                     "WHERE co.case_id=? AND o.type='Person' ORDER BY co.added_at, o.title LIMIT 12", (case.id,)):
        accused = s.query("SELECT COUNT(*) n FROM links WHERE type='accused_in' AND src=?", (r["object_id"],))[0]["n"]
        subjects.append({"id": r["object_id"], "name": r["title"], "accused_in": accused,
                         "basis": "subject of a pattern lead" if (r["reason"] or "").startswith("subject of pattern lead") else (r["reason"] or "")[:80]})
    evidence = [dict(r) for r in s.query("SELECT id, filename, source_type, uploaded_by, uploaded_at, status FROM evidence WHERE case_id=? "
                                         "ORDER BY uploaded_at DESC LIMIT 4", (case.id,))]
    n_evidence = s.query("SELECT COUNT(*) n FROM evidence WHERE case_id=?", (case.id,))[0]["n"]
    n_people = s.query("SELECT COUNT(*) n FROM case_objects co JOIN objects o ON o.id=co.object_id WHERE co.case_id=? AND o.type='Person'",
                       (case.id,))[0]["n"]
    approver = next((u for u in DEV_USERS.values() if u.agency == meta["agency"] and u.has("supervisor") and u.id != c.user.id), None)
    return {"id": case.id, "title": meta.get("title") or case.purpose.replace("_", " "), "purpose": case.purpose, "legal_basis": case.legal_basis,
            "agency": meta.get("agency"), "opened_at": meta.get("opened_at"), "opened_by": meta.get("opened_by"),
            "opened_by_name": _name(meta.get("opened_by")), "depth": case.max_depth, "members": sorted(case.members),
            "people": n_people, "subjects": subjects, "evidence": evidence, "evidence_count": n_evidence,
            "approver": approver.name if approver else None}


def _leads(c: Ctx, cap: int) -> tuple[list[dict[str, Any]], int]:
    s = c.svc.store
    if not L.visible_tracks(s, c.user):
        return [], 0
    reveal = set(c.case.scope) if c.case and c.case.status == "open" and c.user.id in c.case.members else set()
    rows = [dict(r) for r in s.query("SELECT * FROM pattern_hits WHERE status='open'")]
    rows = [r for r in rows if L.can_see(s, c.user, r)]
    rows.sort(key=lambda r: (SEVERITY.get(r["severity"], 9), r["id"]))
    out = []
    for r in rows[:cap]:
        rendered = L.render(s, r, reveal, c.summary, c.decide)
        tracks = ", ".join(json.loads(r["tracks"]))
        out.append(_entry(r["first_seen"], "lead", r["id"], rendered["title"], f"Lead · {r['severity']} · {tracks} track", "proposed", "leads", r["id"]))
    return out, len(rows)


def _approvals(c: Ctx) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Requests waiting for a second officer (entries) and recent human decisions (stamps)."""
    s, u = c.svc.store, c.user
    due, stamps = [], []
    for r in s.query("SELECT * FROM lead_requests WHERE agency=? ORDER BY requested_at DESC LIMIT 30", (u.agency,)):
        r = dict(r)
        title = r.get("title") or "Case from a pattern lead"
        if r["status"] == "pending":
            if u.has("supervisor") and r["requested_by"] != u.id:
                due.append(_entry(r["requested_at"], "approval", r["id"], f"Approve case from lead: {title}",
                                  f"Requested by {_name(r['requested_by'])} · two-person rule", "pending", "leads", r["hit_id"], r["requested_by"]))
            elif r["requested_by"] == u.id:
                due.append(_entry(r["requested_at"], "request", r["id"], f"Your request: {title}",
                                  "Waiting for a supervisor of your agency", "pending", "leads", r["hit_id"], r["requested_by"]))
        elif r["decided_by"]:
            stamps.append({"at": r["decided_at"], "decision": r["status"], "by": r["decided_by"], "by_name": _name(r["decided_by"]),
                           "what": f"Case from lead: {title}", "ref": _short(r["id"]), "requested_by": _name(r["requested_by"])})
    member_cases = [row["case_id"] for row in s.query("SELECT case_id FROM case_members WHERE user_id=?", (u.id,))]
    if member_cases:
        q = ",".join("?" * len(member_cases))
        for r in s.query(f"SELECT * FROM expansion_requests WHERE case_id IN ({q}) ORDER BY requested_at DESC LIMIT 30", member_cases):
            r = dict(r)
            if r["status"] == "pending":
                mine = r["requested_by"] == u.id
                if mine or u.has("supervisor"):
                    due.append(_entry(r["requested_at"], "request" if mine else "approval", r["id"],
                                      (f"Your request: widen {r['case_id']} to depth {r['depth']}" if mine else f"Approve widening {r['case_id']} to depth {r['depth']}"),
                                      r["reason"][:120], "pending", "cases", r["case_id"], r["requested_by"]))
            elif r["decided_by"]:
                stamps.append({"at": r["decided_at"], "decision": r["status"], "by": r["decided_by"], "by_name": _name(r["decided_by"]),
                               "what": f"Widen {r['case_id']} to depth {r['depth']}", "ref": _short(r["id"]), "requested_by": _name(r["requested_by"])})
        for r in s.query(f"SELECT id, case_id, source, summary, requested_by, requested_at, status, decided_by, decided_at FROM intake_proposals "
                         f"WHERE case_id IN ({q}) ORDER BY requested_at DESC LIMIT 30", member_cases):
            r = dict(r)
            summary = json.loads(r["summary"]) if r["summary"] and r["summary"].startswith("{") else {}
            label = f"{r['source']} extract" + (f" · {summary.get('rows')} rows" if summary.get("rows") else "")
            if r["status"] == "pending":
                mine = r["requested_by"] == u.id
                due.append(_entry(r["requested_at"], "request" if mine else "approval", r["id"],
                                  f"Your extract waits to be published: {label}" if mine else f"Approve publishing {label}",
                                  f"Case {r['case_id']} · a second officer must approve", "pending", "studio", r["id"], r["requested_by"]))
            elif r["decided_by"]:
                stamps.append({"at": r["decided_at"], "decision": r["status"], "by": r["decided_by"], "by_name": _name(r["decided_by"]),
                               "what": f"Publish {label}", "ref": _short(r["id"]), "requested_by": _name(r["requested_by"])})
    stamps.sort(key=lambda x: x["at"] or "", reverse=True)
    return due, stamps[:8]


def _review(c: Ctx, cap: int) -> tuple[list[dict[str, Any]], int]:
    if not c.user.has("analyst", "supervisor", "steward"):
        return [], 0
    s = c.svc.store
    n = s.query("SELECT COUNT(*) n FROM review_queue WHERE status='pending'")[0]["n"]
    out = []
    for r in s.query("SELECT id, a, b, probability FROM review_queue WHERE status='pending' ORDER BY probability DESC LIMIT ?", (cap,)):
        objs = s.get_objects([r["a"], r["b"]])
        if r["a"] in objs and r["b"] in objs:
            a, b = c.summary(objs[r["a"]]), c.summary(objs[r["b"]])
            out.append(_entry(None, "match", r["id"], f"Same person? {a['title']} and {b['title']}",
                              f"Match · probability {r['probability']:.2f} · machine proposal", "proposed", "review", r["id"]))
    return out, n


def _oversight(c: Ctx, cap: int) -> list[dict[str, Any]]:
    if not c.user.has("auditor"):
        return []
    out = []
    for a in AuditLog(c.svc.store).alerts()[-cap:][::-1]:
        out.append(_entry(a["ts"], "alarm", f"audit:{a['seq']}", a["detail"], f"{a['rule'].replace('_', ' ')} · {_name(a['user_id'])}",
                          "critical" if a["severity"] == "critical" else "flagged", "oversight", a["user_id"], a["user_id"]))
    for r in c.svc.store.query("SELECT seq, ts, user_id, action FROM audit WHERE outcome='denied' ORDER BY seq DESC LIMIT ?", (cap,)):
        out.append(_entry(r["ts"], "denied", f"audit:{r['seq']}", f"Refused: {r['action'].replace('_', ' ')}", f"{_name(r['user_id'])}",
                          "rejected", "oversight", r["user_id"], r["user_id"]))
    return out


@router.get("/today")
def today(c: Ctx = Depends(get_ctx)) -> dict[str, Any]:
    u = c.user
    cover = _case_cover(c)
    approvals, stamps = _approvals(c)
    leads, n_leads = _leads(c, 8 if u.has("analyst") else 5)
    review, n_review = _review(c, 6 if u.has("steward") else 3)
    alarms = _oversight(c, 12)
    watching = queue_entries(c, _entry)
    # each role reads its own work first; the rest follows in time order
    order = {"supervisor": ["approval", "request", "watch", "search", "lead", "match"], "analyst": ["watch", "search", "lead", "match", "request", "approval"],
             "steward": ["match", "approval", "request", "lead"], "auditor": ["alarm", "denied"],
             "io": ["approval", "watch", "search", "request", "lead", "match"]}.get(u.primary_role, ["approval", "request", "watch", "search", "lead", "match", "alarm", "denied"])
    entries = approvals + watching + leads + review + alarms
    by_kind: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        by_kind.setdefault(e["kind"], []).append(e)
    for v in by_kind.values():
        v.sort(key=lambda e: e["at"] or "", reverse=True)
    entries = [e for k in order for e in by_kind.get(k, [])] + [e for k, v in by_kind.items() if k not in order for e in v]
    counts = {"leads_open": n_leads, "review_pending": n_review,
              "approvals_waiting": sum(1 for e in approvals if e["kind"] == "approval"),
              "requests_waiting": sum(1 for e in approvals if e["kind"] == "request"),
              "alarms": sum(1 for e in alarms if e["mark"] == "critical"), "watching": len(watching)}
    c.log("today", detail={"entries": len(entries[:LIMIT]), "case": cover["id"] if cover else None},
          object_ids=[s["id"] for s in (cover or {}).get("subjects", [])])
    return {"role": u.primary_role, "person": u.public(), "case": cover, "entries": entries[:LIMIT], "stamps": stamps, "counts": counts}
