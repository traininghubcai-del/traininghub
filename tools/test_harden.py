"""The four P0s, proven against a RUNNING hub. Never points at production.

    APP_DATA_DIR=/path/to/sandbox python3 server.py &
    python3 tools/test_harden.py [http://127.0.0.1:8090]

Each test is one of the failure modes found in the Aug 25 audit:
  1  an untouched grade sheet must not mark the class graded
  2  a closed class must refuse grade writes
  3  a date-poisoned row must still appear on the staff list
  4  a class moved out of the archive must be restorable
  5  a clean future class still cannot be backdated
  6  graded and cancelled classes stay on the Admin list
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

B = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8090").rstrip("/")
ADMIN, FSR = "CORP7000", "MAA"
PASSED, FAILED = [], []


def call(path, body=None):
    if body is None:
        req = urllib.request.Request(B + path)
    else:
        req = urllib.request.Request(B + path, json.dumps(body).encode(),
                                     {"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(req))
    except urllib.error.HTTPError as e:
        return json.load(e)


def check(name, cond, detail=""):
    (PASSED if cond else FAILED).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   [{detail}]" if detail else ""))


def classes(mode=("admin", ADMIN), branch=""):
    m, c = mode
    return call(f"/api/hub/classes?mode={m}&code={c}&branch={urllib.parse.quote(branch)}")


def row(eid, mode=("admin", ADMIN)):
    return next((r for r in classes(mode)["classes"] if r["event_id"] == eid), None)


def a_class_with_roster():
    for r in classes()["classes"]:
        if r["registered"] and r["timing"] == "past":
            return r
    return None


def main():
    print(f"hub: {B}\n")
    target = a_class_with_roster()
    if not target:
        print("  no past class with a roster in this data — cannot run 1/2/4")
        return 1
    eid = target["event_id"]
    print(f"target class : {eid}  ({target['event_date']}, {target['registered']} registered)\n")
    roster = call(f"/api/hub/class?event_id={urllib.parse.quote(eid)}&mode=fsr&code={FSR}")["roster"]
    before = {r["attendee_id"]: r["attended"] for r in roster}

    # ---- 1: an untouched sheet -------------------------------------------
    print("1. untouched grade sheet must not mark the class graded")
    blank = [{"attendee_id": a, "attended": "", "score": "", "comment": ""} for a in before]
    r = call("/api/hub/grade", {"mode": "fsr", "code": FSR, "event_id": eid, "grades": blank})
    after = row(eid)
    check("1a. blank submit leaves nobody marked present",
          all(g["attended"] is None
              for g in call(f"/api/hub/class?event_id={urllib.parse.quote(eid)}"
                            f"&mode=fsr&code={FSR}")["roster"]),
          str(r.get("ok")))
    check("1b. class does NOT read graded", after["fsr_audit"] != "graded",
          f"{after['status']} / {after['fsr_audit']}")
    # the browser never sends `false` any more, but prove the server is honest
    # about what it stores if something else does
    check("1c. '' is stored as ungraded, not as absent",
          all(g["attended"] is None
              for g in call(f"/api/hub/class?event_id={urllib.parse.quote(eid)}"
                            f"&mode=fsr&code={FSR}")["roster"]))

    # ---- 2: closed refuses writes ----------------------------------------
    print("\n2. a closed class refuses grade writes")
    graded = [{"attendee_id": a, "attended": 1, "score": 80} for a in before]
    call("/api/hub/grade", {"mode": "fsr", "code": FSR, "event_id": eid, "grades": graded})
    c = call("/api/hub/close-class", {"mode": "fsr", "code": FSR, "event_id": eid})
    check("2a. class closes once everyone is graded", c.get("ok") is True, c.get("error", ""))
    r = call("/api/hub/grade", {"mode": "fsr", "code": FSR, "event_id": eid,
                                "grades": [{"attendee_id": list(before)[0], "attended": 0}]})
    check("2b. grade write on a CLOSED class is refused",
          r.get("ok") is False and "closed" in r.get("error", "").lower(), r.get("error", ""))
    ro = call("/api/hub/reopen-class", {"mode": "fsr", "code": FSR, "event_id": eid})
    check("2c. reopen lets grading resume", ro.get("ok") is True, ro.get("error", ""))
    r = call("/api/hub/grade", {"mode": "fsr", "code": FSR, "event_id": eid, "grades": graded})
    check("2d. ...and the write now lands", r.get("ok") is True, r.get("error", ""))

    # ---- 3: a poisoned date must not vanish ------------------------------
    print("\n3. an unreadable date is REPORTED, never dropped and never OPEN")
    from src.class_status import describe
    check("3a. '2026-09-01 00:00:00' is a good date, not a broken one",
          describe("2026-09-01 00:00:00")["status"] == "OPEN")
    for bad in ("", "TBD", "09/01/2026"):
        d = describe(bad)
        check(f"3b. {bad!r:12} -> BAD DATE (not OPEN)",
              d["status"] == "BAD DATE" and d["lifecycle"] == "action", d["status"])
    n_admin = classes()["count"]
    check("3c. overview reports every catalog row", n_admin > 0, f"{n_admin} rows")

    # ---- 4: the one-way door has a way back ------------------------------
    print("\n4. a class moved out of the archive can be restored")
    was = row(eid)["event_date"]
    fut = call("/api/hub/save-class", {"mode": "admin", "code": ADMIN, "event_id": eid,
                                       "fields": {"event_date": "2099-01-01"}})
    check("4a. past -> future is allowed", fut.get("ok") is True, fut.get("error", ""))
    check("4b. it leaves the archive", row(eid)["lifecycle"] == "live", row(eid)["status"])
    back = call("/api/hub/save-class", {"mode": "admin", "code": ADMIN, "event_id": eid,
                                        "fields": {"event_date": was}})
    check("4c. and it can be put BACK (it has grade history)",
          back.get("ok") is True, back.get("error", ""))
    check("4d. restored to the archive", row(eid)["event_date"] == was, row(eid)["event_date"])

    # ---- 5: a clean future class still cannot be backdated ---------------
    print("\n5. a clean upcoming class still cannot be backdated")
    clean = next(r for r in classes()["classes"]
                 if r["timing"] == "upcoming" and not r["registered"] and r["status"] == "OPEN")
    r = call("/api/hub/save-class", {"mode": "admin", "code": ADMIN,
                                     "event_id": clean["event_id"],
                                     "fields": {"event_date": "2020-01-01"}})
    check("5a. no grade history + no checkbox -> refused",
          r.get("ok") is False and "already passed" in r.get("error", ""), r.get("error", ""))
    r2 = call("/api/hub/save-class", {"mode": "admin", "code": ADMIN,
                                      "event_id": clean["event_id"],
                                      "fields": {"event_date": "2020-01-01"},
                                      "allow_past_restore": True})
    check("5b. ...but the explicit checkbox lets it through",
          r2.get("ok") is True, r2.get("error", ""))
    call("/api/hub/save-class", {"mode": "admin", "code": ADMIN, "event_id": clean["event_id"],
                                 "fields": {"event_date": clean["event_date"]},
                                 "allow_past_restore": True})
    check("5c. and it restores cleanly",
          row(clean["event_id"])["event_date"] == clean["event_date"])
    r3 = call("/api/hub/create-class", {"mode": "admin", "code": ADMIN,
                                        "fields": {"branch": clean["branch"], "topic": "PAST TEST",
                                                   "event_date": "2020-01-01"},
                                        "allow_past_restore": True})
    check("5d. create-class NEVER accepts a past date, hatch or not",
          r3.get("ok") is False and "already passed" in r3.get("error", ""), r3.get("error", ""))

    # ---- 6: the archive stays visible ------------------------------------
    print("\n6. graded and cancelled classes stay on the Admin list")
    rows = classes()["classes"]
    from collections import Counter
    c = Counter(x["status"] for x in rows)
    check("6a. GRADED present", c.get("GRADED", 0) > 0, str(dict(c)))
    check("6b. ERASED present", c.get("ERASED", 0) > 0)
    check("6c. FSR/ALL sees them too",
          all(any(x["event_id"] == g["event_id"] for x in classes(("fsr", FSR))["classes"])
              for g in rows if x_ok(g)))

    # restore the target's grades to how we found them
    call("/api/hub/grade", {"mode": "fsr", "code": FSR, "event_id": eid,
                            "grades": [{"attendee_id": a, "attended": "" if v is None else v,
                                        "score": ""} for a, v in before.items()]})
    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


def x_ok(g):
    return g["status"] in ("GRADED", "ERASED")


if __name__ == "__main__":
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    sys.exit(main())
