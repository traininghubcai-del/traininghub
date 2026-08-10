"""Sync the chat's training-history table from the REAL registrations DB.

Replaces the fabricated seed-42 `registrations_sim.csv` with rows derived live
from `data/registrations.db` (real signups + real grades from registration_attendees).
Dealers and classes are already real projections; this closes the last fake gap so
the TM/Trainer chat runs on 100% real data. "Zero state" is honest: attendees who
haven't been graded yet show status "In Progress" with a blank score — nothing invented.

Run from repo root:
    ./.venv/bin/python tools/sync_chat_from_db.py
then rebuild indexes:
    cd chat_bot && ../.venv/bin/python -m chat_rag.build_index

Join keys (verified 99% match):
    company.account_number  ==  dealers_sim.dealer_id   (both = dealer Customer ID)
    registration.event_id   ->  classes_sim (topic, level)
    dealer's TM (from dealers_sim)  ->  reg.branch / tm_id   (falls back to DB territory_manager)
"""
import csv
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import config  # noqa: E402

CHAT_GLOBAL = REPO / "chat_bot" / "data_global"
OUT = CHAT_GLOBAL / "registrations_sim.csv"

FIELDS = ["reg_id", "event_id", "dealer_id", "attendee_name", "role", "branch",
          "tm_id", "level", "attended", "score", "status", "reg_date"]


def _load_classes():
    """event_id -> (topic, level) from the real class projection."""
    m = {}
    with (CHAT_GLOBAL / "classes_sim.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m[r["event_id"].strip()] = (r.get("topic", "").strip(), r.get("level", "").strip())
    return m


def _load_dealers():
    """dealer_id -> (tm_name/branch, tm_id) from the real dealer projection."""
    m = {}
    with (CHAT_GLOBAL / "dealers_sim.csv").open(newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            m[r["dealer_id"].strip()] = (r.get("branch", "").strip(), r.get("tm_id", "").strip())
    return m


def _tm_id_from_name(name):
    return "tm_" + name.strip().lower().replace(" ", "_") if name.strip() else ""


def _status(graded_at, attended):
    if not graded_at:
        return "In Progress"          # registered, outcome not recorded yet
    return "Completed" if attended == 1 else "No Show"


def build_rows():
    classes = _load_classes()
    dealers = _load_dealers()
    con = sqlite3.connect(config.DB_PATH)
    con.row_factory = sqlite3.Row
    q = """
        SELECT a.id AS aid, a.name AS attendee_name, a.role, a.attended, a.score, a.graded_at,
               r.event_id, r.territory_manager AS db_tm, r.created_at,
               c.account_number
        FROM registration_attendees a
        JOIN registrations r ON r.id = a.registration_id
        JOIN companies c ON c.id = r.company_id
        ORDER BY a.id
    """
    rows, skipped_no_dealer = [], 0
    for x in con.execute(q):
        dealer_id = str(x["account_number"] or "").strip()
        if not dealer_id:
            skipped_no_dealer += 1
            continue
        topic, level = classes.get(x["event_id"], ("", ""))
        # canonical TM comes from the dealer's own record; fall back to the DB field
        branch, tm_id = dealers.get(dealer_id, ("", ""))
        if not branch:
            branch = str(x["db_tm"] or "").strip()
            tm_id = _tm_id_from_name(branch)
        attended = x["attended"]  # 1 / 0 / None
        rows.append({
            "reg_id": f"r{x['aid']:04d}",
            "event_id": x["event_id"],
            "dealer_id": dealer_id,
            "attendee_name": x["attendee_name"] or "",
            "role": x["role"] or "",
            "branch": branch,
            "tm_id": tm_id,
            "level": level,
            "attended": "yes" if attended == 1 else ("no" if attended == 0 else ""),
            "score": "" if x["score"] is None else x["score"],
            "status": _status(x["graded_at"], attended),
            "reg_date": (x["created_at"] or "")[:10],
        })
    con.close()
    return rows, skipped_no_dealer


def main():
    rows, skipped = build_rows()
    with OUT.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    graded = sum(1 for r in rows if r["status"] != "In Progress")
    scored = sum(1 for r in rows if r["score"] != "")
    print(f"Wrote {OUT.relative_to(REPO)}  ({len(rows)} real attendee rows)")
    print(f"  graded (attended recorded): {graded} | with score: {scored} | pending: {len(rows) - graded}")
    if skipped:
        print(f"  skipped {skipped} attendees with no dealer account on file")
    print("Next: cd chat_bot && ../.venv/bin/python -m chat_rag.build_index")


if __name__ == "__main__":
    main()
