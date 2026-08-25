"""Hub modes — one class page, three points of view.

A class used to mean three different screens (register here, grade there, edit
somewhere else). Now it is ONE url — /?event=<id> — with three lenses:

    USER  (blue)    default, no code. Register your team. What a dealer sees.
    ADMIN (orange)  code. Edit the class, seats, address, flier, full roster.
    FSR   (green)   code. Their class: roster, class info, and grading.

Two rules make this real rather than cosmetic:

1. Codes are checked HERE, on the server. The browser never holds the code list,
   so changing a code later means editing data/hub_codes.json — not shipping new
   JavaScript. Admin and FSR have DIFFERENT codes (see DEFAULT_CODES) — an FSR
   grades their branch, an admin can rewrite the schedule, and one shared code
   made those the same privilege. Override either in that file and the app
   picks it up on the next request, no code change.

2. Restricted data is never in the public payload. The roster carries names and
   emails, so it is only ever returned by class_payload() AFTER the code for a
   restricted mode has been verified. Unlocking is not the browser revealing
   something it was already given — it is the server agreeing to send it.
"""
import json
import re

from config import DATA

# Timezone by state, for branches that have no sibling class to copy from.
STATE_TZ = {"AR": "CST", "AL": "CST", "MS": "CST", "LA": "CST", "MO": "CST",
            "OK": "CST", "TX": "CST", "TN": "CST", "KY": "CST", "FL": "CST",
            "GA": "EST", "SC": "EST", "NC": "EST", "VA": "EST", "OH": "EST",
            "IN": "EST", "WV": "EST", "PA": "EST", "NY": "EST", "MI": "EST"}

STORE = DATA / "hub_codes.json"

# What each mode's code is while the team is building. data/hub_codes.json wins
# over this when it exists, so a code change never needs a deploy.
#
# FSR has its OWN code. Admin can edit a live class, cancel it, pull a roster
# and mail dealers; an FSR grades their branch. One shared code made those the
# same privilege — every trainer who could grade could also rewrite the
# schedule. Separate codes is the whole point of separate modes.
DEFAULT_CODES = {
    "user": "",             # unused — the user lens is open to everyone
    "admin": "CORP7000",
    "fsr": "MAA",
}
DEFAULT_CODE = DEFAULT_CODES["admin"]      # legacy alias: admin's code

MODES = {
    "user": {"key": "user", "label": "User", "sub": "Register your team",
             "color": "blue", "restricted": False},
    "admin": {"key": "admin", "label": "Admin", "sub": "Edit class · full roster",
              "color": "orange", "restricted": True},
    "fsr": {"key": "fsr", "label": "FSR", "sub": "Roster · class info · grading",
            "color": "green", "restricted": True},
}


def _codes():
    """{mode: CODE} — file first, DEFAULT_CODES for anything it doesn't set."""
    out = {m: DEFAULT_CODES.get(m, DEFAULT_CODE) for m in MODES}
    if STORE.exists():
        try:
            saved = json.loads(STORE.read_text() or "{}")
            for mode, code in saved.items():
                if mode in out and str(code).strip():
                    out[mode] = str(code).strip()
        except (ValueError, OSError):
            pass                      # unreadable file -> fall back to defaults
    return out


def mode_list():
    """The three lenses, for the switcher. Never includes any code."""
    return [dict(MODES[m]) for m in ("user", "admin", "fsr")]


def verify(mode, code):
    """True when this code opens this mode. 'user' is open to everyone."""
    mode = str(mode or "user").strip().lower()
    if mode not in MODES:
        return False
    if not MODES[mode]["restricted"]:
        return True
    want = _codes()[mode].strip()
    if not want:
        return False        # a restricted mode with no code configured opens for nobody
    return str(code or "").strip().upper() == want.upper()


def unlock(mode, code):
    mode = str(mode or "").strip().lower()
    if mode not in MODES:
        return {"ok": False, "error": "Unknown view."}
    if not verify(mode, code):
        return {"ok": False, "error": f"That code doesn't open the {MODES[mode]['label']} view."}
    return {"ok": True, "mode": mode, **MODES[mode]}


# ---------------------------------------------------------------- payloads --

def class_payload(repo, event_id, mode, code):
    """Everything one mode is allowed to see for one class.

    The gate is here, not in the browser: fail verify() and no roster, no
    emails, no grades leave the process.
    """
    from src.catalog import event_view, is_active, load_catalog

    mode = str(mode or "user").strip().lower()
    if mode not in MODES:
        return {"ok": False, "error": "Unknown view."}
    if not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": mode}

    events, branches, _ = load_catalog()
    ev = events.get(str(event_id).strip())
    if not ev:
        return {"ok": False, "error": "This class link is not active."}

    # A cancelled class stays open to Admin — they need the roster to tell the
    # dealers, and the Reinstate button lives in this payload. Cancelling would
    # otherwise be a one-way door with the attendee list locked inside it.
    cancelled = not is_active(ev)
    if cancelled and mode != "admin":
        return {"ok": False, "error": "This class link is not active."}

    from src.contacts import support_for
    from src.fliers import get_flier
    view = event_view(ev)
    view["support"] = support_for(ev)
    out = {"ok": True, "mode": mode, "event": view, "branches": branches,
           "cancelled": cancelled, "flier": get_flier(view["event_id"])}

    if mode == "user":
        return out                              # public only — no roster, no emails

    # restricted from here down
    eid = view["event_id"]
    out["seats"] = _seats(repo, ev, eid)
    out["roster"] = _graded_roster(repo, eid)
    out["status"] = class_status(repo, ev, eid, out["roster"])
    if mode == "admin":
        out["edit"] = _edit_fields(ev, eid)
    return out


def class_status(repo, ev, event_id, roster):
    """Where this class sits in its life cycle, for the class page.

      status   : the pill — OPEN/TODAY/TOMORROW/NOT-GRADED/GRADED/NO SIGNUPS/ERASED
      lifecycle: live | action | archive   (the derived archive)
      timing   : past | today | upcoming   (grading only opens once it's past)
      grading  : graded | needs_grading | n/a

    status/lifecycle come from src.class_status — the SAME call the master list
    makes — so a class cannot wear one label in the list and another on its own
    page. timing/grading stay because the FSR grade sheet is wired to them.
    """
    from src.catalog import is_active
    from src.class_status import describe

    total = len(roster)
    done = sum(1 for r in roster if r.get("attended") is not None)
    st = describe(str(ev.get("event_date", ""))[:10], active=is_active(ev),
                  registered=total, graded_count=done)
    timing = st["timing"]

    if timing != "past" or not total:
        grading = "n/a"
    elif done == total:
        grading = "graded"
    else:
        grading = "needs_grading"

    return {
        "status": st["status"],
        "status_css": st["status_css"],
        "lifecycle": st["lifecycle"],
        "fsr_audit": st["fsr_audit"],
        "fsr_audit_css": st["fsr_audit_css"],
        "timing": timing,
        "grading": grading,
        "graded_count": done,
        "graded_total": total,
        "can_grade": timing == "past" and total > 0,
        "closed_at": repo.class_closed_at(event_id),
    }


def close_class(repo, event_id, mode, code):
    """Final step: lock the class. Attendance, pass/fail and scores are done.

    There is no mail system yet, so closing IS the finish line — no surveys are
    sent. When email is wired up this is the hook the sender attaches to.
    """
    if mode not in ("fsr", "admin") or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True}
    roster = repo.class_grades(event_id)
    if not roster:
        return {"ok": False, "error": "Nobody is registered for this class."}
    ungraded = [r["name"] for r in roster if r.get("attended") is None]
    if ungraded:
        return {"ok": False, "error": (
            f"{len(ungraded)} student(s) still ungraded — submit the class info first.")}
    if repo.class_closed_at(event_id):
        return {"ok": False, "error": "This class is already closed."}

    closed_at = repo.mark_class_closed(event_id)
    from src.audit import log
    log(mode, "class.close", event_id, {"closed_at": closed_at})
    attended = sum(1 for r in roster if r.get("attended") == 1)
    passed = sum(1 for r in roster if r.get("passed") == 1)
    return {"ok": True, "closed_at": closed_at,
            "message": (f"Class closed. {attended} of {len(roster)} attended, "
                        f"{passed} passed.")}


def reopen_class(repo, event_id, mode, code):
    """Unlock a closed class so a grade can be corrected."""
    if mode not in ("fsr", "admin") or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True}
    if not repo.class_closed_at(event_id):
        return {"ok": False, "error": "This class isn't closed."}
    repo.reopen_class(event_id)
    from src.audit import log
    log(mode, "class.reopen", event_id)
    return {"ok": True, "message": "Class reopened — grades can be edited again."}


def create_class(repo, mode, code, fields):
    """Add a class from the master list. Admin only.

    Goes through src.manage.create_class — the one catalog write path — so the
    new class inherits its region's branch/state/timezone/venue and lands with
    every capability already populated.
    """
    if mode != "admin" or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": "admin"}

    fields = dict(fields or {})
    region = str(fields.get("region", "")).strip()
    topic = str(fields.get("topic", "")).strip()
    date = str(fields.get("event_date", "")).strip()
    branch = str(fields.get("branch", "")).strip()
    if not branch:
        return {"ok": False, "error": "Pick a branch, or type a new one."}
    if not region:
        # a brand-new branch has no sibling to copy from: "Conway, AR" -> "Conway"
        region = re.sub(r",\s*[A-Z]{2}\s*$", "", branch).strip()
        region = re.sub(r"^\s*\d+\s*[-\u2013]\s*", "", region).strip()
        fields["region"] = region
    if not region:
        return {"ok": False, "error": "Give the branch a region name."}
    if not topic:
        return {"ok": False, "error": "Give the class a name."}
    if not date:
        return {"ok": False, "error": "Pick a date."}

    # Date/time legality is not decided here — src.class_schedule owns it, so
    # this screen and the workbook writer refuse the same things in the same
    # words. (src.manage re-checks; this is only to fail before the branch and
    # timezone questions below.)
    from src.class_schedule import refuse_bad_schedule
    err = refuse_bad_schedule(date, fields.get("start_time"), fields.get("end_time"))
    if err:
        return {"ok": False, "error": err}

    cap = str(fields.get("capacity", "")).strip()
    if cap:
        try:
            if int(float(cap)) <= 0:
                return {"ok": False, "error": "Capacity has to be at least 1."}
        except (ValueError, TypeError):
            return {"ok": False, "error": "Capacity must be a whole number."}

    # A new branch inherits nothing, so it must carry its own timezone —
    # otherwise the class renders a time with no zone and a dealer can read the
    # wrong hour. Derive from the state when we can, else demand it.
    known = {b["branch"] for b in branch_options()}
    if branch not in known:
        state = str(fields.get("state", "")).strip().upper()
        if not state:
            m = re.search(r",\s*([A-Z]{2})\s*$", branch)
            state = m.group(1) if m else ""
            fields["state"] = state
        tz = str(fields.get("timezone", "")).strip().upper()
        if not tz:
            tz = STATE_TZ.get(state, "")
            fields["timezone"] = tz
        if not tz:
            return {"ok": False, "error": (
                f"“{branch}” is a new branch — set its timezone (CST or EST) so class "
                f"times show correctly.")}

    # a floating address is an overlay, never a catalog column
    address = str(fields.pop("class_address", "") or "").strip()

    from src.audit import log
    from src.manage import create_class as _create
    result = _create(repo, fields)
    if result.get("ok"):
        log(mode, "class.create", result["class"]["event_id"],
            {"topic": topic, "branch": fields.get("branch"), "date": date,
             "capacity": fields.get("capacity"), "address": address or None})
    if result.get("ok") and address:
        from src.class_address import set_address
        set_address(result["class"]["event_id"], address)
        result["class"]["class_address"] = address
    return result


def branch_options():
    """Branches from the catalog, each with the region + state it implies, so
    picking a branch fills in the rest of the class for you."""
    from src.catalog import is_active, load_catalog
    events, branches, _ = load_catalog()
    by_branch = {}
    for ev in events.values():
        if not is_active(ev):
            continue
        b = str(ev.get("branch", "")).strip()
        if b and b not in by_branch:
            by_branch[b] = {"branch": b,
                            "region": str(ev.get("region", "")).strip(),
                            "state": str(ev.get("state", "")).strip(),
                            "location": str(ev.get("event_location", "")).strip()}
    out = [by_branch[b] for b in branches if b in by_branch]
    out += [v for k, v in by_branch.items() if k not in set(branches)]
    return out


def set_branch_phone(mode, code, branch, phone):
    """Admin sets the support number shown on every class at that branch."""
    if mode != "admin" or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": "admin"}
    from src.audit import log
    from src.contacts import set_phone
    result = set_phone(branch, phone)
    if result.get("ok"):
        log(mode, "branch.phone", result["branch"], {"phone": result["phone"]})
    return result


def remove_registration(repo, mode, code, registration_id):
    """Take a company (and its attendees) off a class. Admin only."""
    if mode != "admin" or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": "admin"}
    try:
        rid = int(registration_id)
    except (TypeError, ValueError):
        return {"ok": False, "error": "Missing registration."}
    from src.audit import log
    snapshot = repo.registration_snapshot(rid)
    removed = repo.delete_registration(rid)
    if not removed:
        return {"ok": False, "error": "That registration no longer exists."}
    log(mode, "registration.remove", (snapshot or {}).get("event_id", ""), snapshot)
    try:
        from src.export import write_registrations_xlsx
        write_registrations_xlsx(repo)          # keep the Excel mirror in step
    except Exception:  # noqa: BLE001 - the DB is the source of truth either way
        pass
    return {"ok": True, "message": "Removed from the class."}


def reminder_letters(repo, event_id, mode, code, only_attending=True):
    """Build one reminder-letter URL per student and log the run.

    Generating IS the send while there is no mail system: staff opens each PDF
    and prints or forwards it. So this writes to the campaign ledger, which is
    what drives the "reminders sent" / "last reminder" columns.
    """
    if mode != "admin" or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": "admin"}

    from src.catalog import event_view, is_active, load_catalog
    events, _, _ = load_catalog()
    ev = events.get(str(event_id).strip())
    if not ev or not is_active(ev):
        return {"ok": False, "error": "This class isn't active."}
    view = event_view(ev)

    roster = repo.class_grades(view["event_id"])
    if only_attending:
        # nobody graded yet -> everyone on the roster is still expected to attend
        marked = [r for r in roster if r.get("attended") is not None]
        students = [r for r in roster if r.get("attended") == 1] if marked else roster
    else:
        students = roster

    if not students:
        return {"ok": False, "error": "No students to generate letters for."}

    from src.audit import log
    from src.reminder_letters import log_generated
    logged = log_generated(students, view)
    log(mode, "reminders.generate", view["event_id"], {"letters": len(students)})

    from urllib.parse import quote
    urls = [{
        "attendee_id": s["attendee_id"],
        "name": s["name"],
        "url": (f"/reminder-letter?event_id={quote(view['event_id'])}"
                f"&attendee_id={s['attendee_id']}&mode=admin&code={quote(code)}"),
    } for s in students]

    return {"ok": True, "count": len(urls), "letters": urls,
            "days_until": logged["days_until"],
            "message": (f"{len(urls)} reminder letter{'' if len(urls) == 1 else 's'} generated "
                        f"and logged as sent.")}


def letter_pdf(repo, event_id, attendee_id, mode, code):
    """One student's letter as PDF bytes. Gated like everything else."""
    if mode != "admin" or not verify(mode, code):
        return None, None

    from src.catalog import event_view, is_active, load_catalog
    events, _, _ = load_catalog()
    ev = events.get(str(event_id).strip())
    if not ev or not is_active(ev):
        return None, None
    view = event_view(ev)

    roster = repo.class_grades(view["event_id"])
    from src.reminder_letters import build_context, render_pdf

    try:
        aid = int(attendee_id)
    except (TypeError, ValueError):
        return None, None
    student = next((r for r in roster if r["attendee_id"] == aid), None)
    if not student:
        return None, None
    ctx = build_context(student, view)
    return render_pdf(ctx), ctx


def classes_overview(repo, mode, code, branch=""):
    """The master class table: every class, with the operational numbers the
    public list deliberately hides — who's registered, how full it is, and the
    one computed status that says where it sits right now.

    ONE table serves both restricted lenses. Admin gets the whole ledger; FSR
    gets it filtered to a branch (see `branch`). Each mode is still verified
    against its OWN code, so sharing the table is not sharing the key. This is
    read-only; every write stays admin-only.

    Cancelled classes are INCLUDED here (they read ERASED) — hiding them is how
    a bad cancel goes unnoticed. The public feed still never sees them.
    """
    if mode not in ("admin", "fsr") or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": mode or "admin"}

    from src.catalog import event_view, is_active, load_catalog
    from src.class_status import describe
    from src.reminders import reminder_stats

    events, _, _ = load_catalog()
    rem = reminder_stats()          # one read of the campaign ledger for all classes
    want_branch = str(branch or "").strip()
    if want_branch.upper() in ("", "ALL"):
        want_branch = ""
    rows = []
    for ev in events.values():
        # no date cut and no active cut on purpose — finished and cancelled
        # classes are exactly what this view exists to show
        if want_branch and str(ev.get("branch", "")).strip() != want_branch:
            continue
        try:
            v = event_view(ev)
        except Exception as exc:  # noqa: BLE001
            # A row that cannot be rendered must still be REPORTED. Skipping it
            # is how a class silently disappears from every staff screen with
            # no error and no count to notice it went. Emit the least we know.
            eid = str(ev.get("event_id", "")).strip()
            if not eid:
                continue
            v = {"event_id": eid, "topic": str(ev.get("topic", "")) or "(unreadable row)",
                 "region": str(ev.get("region", "")), "branch": str(ev.get("branch", "")),
                 "event_date": "", "event_date_raw": str(ev.get("event_date", "")),
                 "date_display": "Unreadable", "date_short": "??", "time_display": "—",
                 "trainer": str(ev.get("trainer", "")), "event_location": "",
                 "class_address": "", "notes": "", "weekday_display": "",
                 "date_info": "", "needs_info": True, "missing": ["row"],
                 "bad_date": True, "broken": f"{type(exc).__name__}: {exc}"}
        eid = v["event_id"]
        roster = repo.class_grades(eid)
        try:
            cap = int(float(ev.get("capacity") or 0))
        except (ValueError, TypeError):
            cap = 0
        total = len(roster)
        done = sum(1 for r in roster if r.get("attended") is not None)
        active = is_active(ev)
        # the single derivation — src.class_status owns the whole vocabulary.
        # event_date_raw, not event_date: a row whose date could not be parsed
        # has event_date "" and MUST come back BAD DATE, not be quietly dated.
        st = describe(v.get("event_date") or v.get("event_date_raw", ""),
                      active=active, registered=total, graded_count=done)
        timing = st["timing"]
        # The display fields ride along with the operational ones so the master
        # list can render straight from this response. It has to: the public
        # /api/events feed has no past classes in it, and a finished class is
        # exactly the one an FSR came here to grade.
        rows.append({
            **v,
            "event_id": eid,
            "registered": total,
            "capacity": cap,
            "seats_left": max(0, cap - total) if cap else None,
            "companies": len({r["company_name"] for r in roster if r["company_name"]}),
            "timing": timing,
            "graded_count": done,
            "active": active,
            # computed every response, stored nowhere: STATUS is the pill, and
            # LIFECYCLE is the archive (live / action / archive)
            "status": st["status"],
            "status_css": st["status_css"],
            "lifecycle": st["lifecycle"],
            # the FSR-Audit column: is a grade owed here, done, or not a
            # question yet. Derived from status, never stored.
            "fsr_audit": st["fsr_audit"],
            "fsr_audit_css": st["fsr_audit_css"],
            "bad_date": bool(v.get("bad_date")),
            "event_date_raw": v.get("event_date_raw", ""),
            "grading": ("n/a" if timing != "past" or not total
                        else "graded" if done == total else "needs_grading"),
            "closed_at": repo.class_closed_at(eid),
            # reminder history comes straight from the email campaign's outbox
            # ledger, so these go live the moment real sending is switched on
            "reminders_sent": rem.get(eid, {}).get("sent", 0),        # RUNS, not letters
            "reminder_letters": rem.get(eid, {}).get("letters", 0),
            "last_reminder_at": rem.get(eid, {}).get("last_sent_at", ""),
            "last_reminder": rem.get(eid, {}).get("last_sent_display", ""),
            "reminder_stages": rem.get(eid, {}).get("stages", []),
        })
    # STRICT CHRONOLOGICAL ORDER. Not status buckets.
    #
    # Ranking by status quietly re-arranged the calendar: a finished class
    # dropped to an "archive block" at the bottom no matter what month it was
    # in, so August and October sat next to each other and the list stopped
    # reading as a schedule. The status is already a column — it does not need
    # to be the sort as well.
    #
    # A row whose date could not be read has event_date "" and therefore sorts
    # FIRST. That is deliberate: it is the one row nobody should have to scroll
    # to find.
    rows.sort(key=lambda r: (r["event_date"] or "", r["event_id"]))
    return {"ok": True, "classes": rows, "branches": branch_options(),
            "branch": want_branch, "count": len(rows)}


def _seats(repo, ev, event_id):
    try:
        cap = int(float(ev.get("capacity") or 0))
    except (ValueError, TypeError):
        cap = 0
    try:
        taken = int(repo.seats_taken(event_id))
    except Exception:  # noqa: BLE001
        taken = 0
    return {"capacity": cap, "taken": taken, "left": max(0, cap - taken) if cap else None}


def _edit_fields(ev, event_id):
    """The same field set /manage edits, so both write through src.manage."""
    from src.class_address import get_address
    return {
        "topic": ev.get("topic", ""),
        "region": ev.get("region", ""),
        "branch": ev.get("branch", ""),
        "event_date": str(ev.get("event_date", ""))[:10],
        "start_time": str(ev.get("start_time", "")),
        "end_time": str(ev.get("end_time", "")),
        "trainer": str(ev.get("trainer", "")).strip(),
        "capacity": ev.get("capacity", ""),
        "event_location": ev.get("event_location", ""),
        "class_address": get_address(event_id),
        "notes": ev.get("notes", ""),
    }


def _graded_roster(repo, event_id):
    """One row per student, with whatever grading has been saved. This is the
    shape both the FSR grading screen and the admin roster read."""
    return repo.class_grades(event_id)


def save_class(repo, event_id, mode, code, fields, allow_past_restore=False):
    """Admin-mode class edit. The ADMIN code already proved authority here, so
    this does not ask again for the Edits & Updates code — it goes straight to
    src.manage.update_class, the one write path for the catalog (and the one
    place that knows class_address is an overlay, not a column)."""
    if mode != "admin" or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": "admin"}
    from src.audit import log
    from src.manage import update_class
    before = _edit_snapshot(event_id)
    result = update_class(repo, event_id, fields or {}, allow_past_restore)
    if result.get("ok"):
        log(mode, "class.update", event_id,
            {"changed": result.get("changed", []),
             "from": {k: before.get(k) for k in result.get("changed", [])},
             "to": {k: (fields or {}).get(k) for k in result.get("changed", [])}})
    return result


def send_class_reminders(repo, event_id, mode, code):
    """Email everyone registered for this class the "it's coming up" reminder,
    now, instead of waiting for the 7/3/1-day schedule to reach them.

    One email per registration, never one per stage: whichever stage sits
    closest to today is the one that goes, so the wording matches how far off
    the class actually is. Anything already in the ledger is skipped, and what
    does go out is written back to that same ledger — so pressing this button
    cannot produce a second copy, and neither can tonight's scheduled run.
    """
    if mode != "admin" or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": "admin"}

    from datetime import date

    from src.audit import log
    from src.email_campaign import reminded_today, send_jobs, sent_keys, upcoming_jobs

    event_id = str(event_id).strip()
    today = date.today()
    jobs = [j for j in upcoming_jobs(today) if j["view"]["event_id"] == event_id]
    if not jobs:
        return {"ok": False, "error": "Nobody is registered yet, or the class has already passed."}

    done = sent_keys()
    already = reminded_today(event_id, today)   # stops an accidental double-click
    nearest = {}
    for j in jobs:
        if j["reg_id"] in already or (j["reg_id"], j["stage"]) in done:
            continue                       # that dealer already heard from us
        best = nearest.get(j["reg_id"])
        if best is None or abs((j["send_on"] - today).days) < abs((best["send_on"] - today).days):
            nearest[j["reg_id"]] = j
    picked = list(nearest.values())
    if not picked:
        return {"ok": True, "sent": 0, "simulated": 0, "failed": 0,
                "message": "Everyone registered has already had a reminder today."}

    results = send_jobs(picked, today)
    sent = [r for r in results if str(r["status"]).startswith("SENT")]
    simulated = [r for r in results if str(r["status"]).startswith("SIMULATED")]
    failed = [r for r in results if str(r["status"]).startswith("FAILED")]
    log(mode, "class.remind_email", event_id,
        {"sent": len(sent), "simulated": len(simulated), "failed": len(failed)})

    if simulated:
        msg = (f"Simulated {len(simulated)} reminder(s) — email sending is switched off, "
               "so nothing left the server.")
    elif failed and sent:
        msg = f"Sent {len(sent)}, but {len(failed)} failed. Failed ones retry automatically."
    elif failed:
        msg = f"Couldn't send — {failed[0]['status']}"
    else:
        msg = f"Reminder emailed to {len(sent)} registered dealer(s)."
    return {"ok": not (failed and not sent), "sent": len(sent),
            "simulated": len(simulated), "failed": len(failed), "message": msg}


_TRUE_WORDS = {"true", "1", "yes", "on"}
_FALSE_WORDS = {"false", "0", "no", "off"}


def _as_bool(value):
    """Strict boolean, or None when the value does not clearly mean either.

    bool("false") is True in Python, so a client sending the STRING "false"
    would REINSTATE the class it meant to cancel. Cancel and reinstate are
    opposite, dealer-visible actions — one hides a class, the other reopens
    registration — so an unclear value is refused, never guessed at.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value if value is not None else "").strip().lower()
    if text in _TRUE_WORDS:
        return True
    if text in _FALSE_WORDS:
        return False
    return None


def set_class_active(repo, event_id, mode, code, active):
    """Cancel (active=False) or reinstate (active=True) one class.

    Cancelling is deliberately non-destructive: registrations, grades and seat
    counts are all left alone, so a class taken down by mistake comes back
    exactly as it was. It only hides the class from dealers, refuses new
    signups, and stops the reminder emails.
    """
    if mode != "admin" or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True, "mode": "admin"}
    from src.audit import log
    from src.manage import set_active
    event_id = str(event_id).strip()
    active = _as_bool(active)
    if active is None:
        return {"ok": False, "error": "Unclear 'active' value — send true or false."}
    result = set_active(repo, event_id, active)
    if result.get("ok"):
        log(mode, "class.reinstate" if active else "class.cancel", event_id,
            {"active": active})
    return result


def _edit_snapshot(event_id):
    """The class's current editable values — captured before a write so the
    audit entry can say what it changed FROM, not just to."""
    try:
        from src.catalog import load_catalog
        ev = load_catalog()[0].get(str(event_id).strip())
        return _edit_fields(ev, event_id) if ev else {}
    except Exception:  # noqa: BLE001
        return {}


# What an admin gets told when they try to write a grade. One string, used by
# the API and echoed by the browser, so the two never say different things.
GRADE_IS_FSR_ONLY = "Start from FSR-VIEW to grade class"


def save_grades(repo, event_id, mode, code, grades, graded_by=""):
    """Persist per-student attendance / score / comment. FSR ONLY.

    Admin can SEE what's outstanding — the FSR-Audit column on the master list
    is built for exactly that — but cannot write a grade. A grade is a
    trainer's judgement about a student who stood in their room; an admin who
    was not there has no basis for it, and a shared grade button is how one
    ends up entered by whoever happened to be logged in.

    Enforced here, not in the browser: hiding the button is a UI preference,
    refusing the write is a rule.
    """
    if mode == "admin":
        return {"ok": False, "error": GRADE_IS_FSR_ONLY, "fsr_only": True}
    if mode != "fsr" or not verify(mode, code):
        return {"ok": False, "error": "Locked.", "need_code": True}
    if not str(event_id).strip():
        return {"ok": False, "error": "Missing event_id."}

    # Closing a class is supposed to make its grades FINAL. It used to only
    # disable a button, and the API went on accepting writes — so "closed"
    # described the screen, not the data. Reopen is the way back in.
    if repo.class_closed_at(event_id):
        return {"ok": False, "error": "Class is closed. Reopen to change grades.",
                "closed": True}

    clean = []
    for g in (grades or []):
        try:
            aid = int(g.get("attendee_id"))
        except (TypeError, ValueError):
            continue
        attended = g.get("attended")
        attended = None if attended in (None, "") else (1 if attended in (True, 1, "1", "true", "yes") else 0)

        score = g.get("score")
        if score in (None, ""):
            score = None
        else:
            try:
                score = max(0.0, min(100.0, float(score)))
            except (TypeError, ValueError):
                return {"ok": False, "error": "Scores must be a number from 0 to 100."}

        # Pass/fail: the trainer's explicit call wins (they may pass someone on
        # hands-on work with no score). Falls back to the 70% rule when they
        # leave it on "—" and a score is present.
        raw_pass = g.get("passed")
        if raw_pass in (1, "1", True, "pass", "Pass"):
            passed = 1
        elif raw_pass in (0, "0", False, "fail", "Fail"):
            passed = 0
        elif attended != 1 or score is None:
            passed = None
        else:
            passed = 1 if score >= 70 else 0
        if attended == 0:
            passed = 0                      # a no-show never passes
        clean.append({"attendee_id": aid, "attended": attended, "score": score,
                      "passed": passed, "comment": str(g.get("comment", "") or "").strip()})

    if not clean:
        return {"ok": False, "error": "Nothing to save."}

    n = repo.save_grades(event_id, clean, graded_by or mode)
    from src.audit import log
    log(mode, "grades.save", event_id, {"students": n})
    roster = repo.class_grades(event_id)
    from src.catalog import load_catalog
    ev = load_catalog()[0].get(event_id) or {"event_date": ""}
    return {"ok": True, "saved": n,
            "message": f"Saved grades for {n} student{'' if n == 1 else 's'}.",
            "roster": roster,
            "status": class_status(repo, ev, event_id, roster)}
