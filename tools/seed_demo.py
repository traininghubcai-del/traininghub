"""Seed a FULL demo dataset: every program dealer participates in training.

Builds a believable 3-month story over the current events.xlsx catalog:
  - each dealer gets a fixed crew of 2–5 named employees (deterministic, seed 42),
    and the same names re-register across classes → real "returning student" stats
  - past classes get graded: the oldest fully (green check), the recent one
    partially (yellow dot); attendance ~85%, pass when score ≥ 70
  - today's + upcoming classes hold ungraded registrations

Server must be RUNNING (registrations go through the real /api/register, so
account #s + TMs resolve exactly like production). Grades are written straight
into registration_attendees afterwards.

Run:  ./.venv/bin/python tools/seed_demo.py        # assumes localhost:8000
"""
import json
import random
import sqlite3
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import DB_PATH                      # noqa: E402
from src.admin_hub import _home_tms              # noqa: E402
from src.catalog import is_active, load_catalog  # noqa: E402
from src.dealers import dealer_directory, find_dealer  # noqa: E402

BASE = "http://localhost:8000"
rng = random.Random(42)

FIRST = ["James", "Maria", "Chris", "Dana", "Alex", "Tyler", "Sam", "Jordan", "Casey",
         "Luis", "Tony", "Rachel", "Mike", "Sarah", "Kevin", "Beth", "Carlos", "Amy",
         "Derek", "Nina", "Paul", "Tasha", "Ray", "Holly"]
LAST = ["Hayes", "Lopez", "Vance", "Frye", "Marsh", "Dill", "Stone", "Berry", "Cole",
        "Ortiz", "Lane", "Webb", "Carter", "Boyd", "Reyes", "Mills", "Snow", "Drake",
        "Page", "Knox", "Hale", "Moss", "York", "Drew"]
ROLES = ["Technician", "Technician", "Technician", "Inside Sales", "Outside Sales", "Owner"]
COMMENTS = ["Solid work — ready for the next level", "Sharp questions, engaged all day",
            "Needs more bench time on brazing", "Great with diagnostics flow",
            "On time, good fundamentals", "Struggled with the wiring lab — refresher recommended"]


def crew_for(dealer):
    """Deterministic 2–5 person crew per dealer — same names every run."""
    r = random.Random(dealer["customer_id"])
    n = r.choice([2, 3, 3, 4, 5])
    return [{"name": f"{r.choice(FIRST)} {r.choice(LAST)}", "role": r.choice(ROLES)}
            for _ in range(n)]


def register(event_id, dealer, branch, attendees):
    slug = "".join(ch for ch in dealer["company_name"].lower() if ch.isalnum())[:14]
    payload = {"event_id": event_id, "contact_email": f"training@{slug}.com",
               "company_name": dealer["company_name"], "customer_id": dealer["customer_id"],
               "branch": branch, "attendees_list": attendees}
    req = urllib.request.Request(f"{BASE}/api/register", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp).get("ok", False)


def main():
    dealers = dealer_directory()
    events, branches, _ = load_catalog()
    classes = sorted((e for e in events.values() if is_active(e)),
                     key=lambda e: str(e["event_date"]))
    today = date.today().isoformat()

    # every dealer trains 1–3 times; heavier turnout for past + today classes
    participations = []
    for d in dealers:
        for _ in range(rng.choice([1, 1, 2, 2, 3])):
            participations.append(d)
    rng.shuffle(participations)

    # honour each class's capacity — the server now rejects overflow anyway,
    # so track seats locally and stop filling classes that are full
    seats = {c["event_id"]: 0 for c in classes}
    # past classes ran full; upcoming ones keep 3-5 open seats so a live
    # registration can still be demoed on stage
    caps = {}
    for c in classes:
        cap = int(c.get("capacity") or 16)
        if str(c["event_date"])[:10] > today:
            cap = max(1, cap - rng.choice([3, 4, 5]))
        caps[c["event_id"]] = cap
    # dealers mostly train at their TM's home branch (×8 weight), occasionally
    # travel — so each location's numbers are dominated by its own TM's dealers
    regions = {c["region"] for c in classes}
    tm_home = {}
    for region in regions:
        for tm in _home_tms(region):
            tm_home[tm] = region

    total_regs = 0
    for d in participations:
        dealer = find_dealer(customer_id=d["customer_id"])
        home = tm_home.get(dealer["territory_manager"] if dealer else "", "")
        # dealers whose TM has no class at home rarely travel — keeps the
        # "Other" bucket small so the named TMs own their locations' numbers
        if not home and rng.random() < 0.75:
            continue
        open_classes = [c for c in classes if seats[c["event_id"]] < caps[c["event_id"]]]
        if not open_classes:
            break
        weights = [(40 if c["region"] == home else 1) *
                   (2 if str(c["event_date"])[:10] <= today else 1)
                   for c in open_classes]
        ev = rng.choices(open_classes, weights=weights, k=1)[0]
        room = caps[ev["event_id"]] - seats[ev["event_id"]]
        crew = crew_for({"customer_id": d["customer_id"], "company_name": d["company_name"]})
        k = min(len(crew), rng.choice([1, 1, 2, 2, 3]), room)
        team = rng.sample(crew, k=k)
        if register(ev["event_id"], d, ev["branch"], team):
            total_regs += 1
            seats[ev["event_id"]] += len(team)

    # ---- grade the past classes -------------------------------------------------
    # only the two oldest get grades (one fully ✅, one partially 🟡) — every other
    # finished class stays UNGRADED so there are fresh grade sheets to demo with
    past = [c for c in classes if str(c["event_date"])[:10] < today]
    con = sqlite3.connect(DB_PATH)
    now = datetime.now().isoformat(timespec="seconds")
    graded_rows = 0
    for i, ev in enumerate(past[:2]):
        ids = [r[0] for r in con.execute(
            """SELECT a.id FROM registration_attendees a
               JOIN registrations r ON a.registration_id = r.id
               WHERE r.event_id = ?""", (ev["event_id"],))]
        portion = ids if i == 0 else rng.sample(ids, k=max(1, int(len(ids) * .6)))
        for aid in portion:
            attended = rng.random() < 0.85
            score = rng.randint(52, 98) if attended else None
            passed = 1 if (attended and score >= 70) else 0
            con.execute(
                """UPDATE registration_attendees SET attended=?, passed=?, score=?,
                   comment=?, graded_by='trainer_ward', graded_at=? WHERE id=?""",
                (1 if attended else 0, passed, score,
                 rng.choice(COMMENTS) if attended else "No show", now, aid))
            graded_rows += 1
    con.commit()
    con.close()

    print(f"registrations: {total_regs}  (dealers: {len(dealers)})")
    print(f"graded students: {graded_rows} across {len(past)} past classes")


if __name__ == "__main__":
    main()
