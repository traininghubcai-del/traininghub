"""Email-campaign demo & troubleshooting console (no server needed).

    ./.venv/bin/python email_demo.py

Menu:
  1) generate every reminder email (7/3/1 days, HTML + .ics per student)
  2) run the sender for any "today" you type — simulated send: each due email
     becomes a row in data/email_campaign/outbox.xlsx (what a daily cron will
     do for real after deploy)
  3) campaign status — planned vs sent, next send dates
  4) open a generated email in the browser
  5) seed demo registrations (only offered while the DB is empty)

Headless mode (what a daily cron/launchd job calls after deploy — no menu,
regenerates emails then sends whatever is due as of the real today):

    ./.venv/bin/python email_demo.py send

Everything it writes lives under data/email_campaign/ and is regenerable.
"""
import sys
import webbrowser
from datetime import date, datetime

from config import CAMPAIGN_OUTBOX_XLSX, CAMPAIGN_SCHEDULE_XLSX, EMAIL_OUT_DIR
from src.db import get_repository
from src.email_campaign import due_jobs, generate_emails, run_sender, sent_keys, upcoming_jobs
from src.export import write_registrations_xlsx
from src.registrations import build_registration

# Demo dealers across the upcoming June/July classes. Saved through the real
# pipeline (build_registration -> repo), so the campaign reads true rows.
DEMO_REGS = [
    ("columbia-fit-2026-06-17", "service@hvacprosllc.example", "HVAC Pros LLC",
     "44021", "125- Columbia",
     [("Mike Torres", "Technician"), ("Deshawn Carter", "Technician")]),
    ("columbia-fit-2026-06-17", "office@comfortworks.example", "ComfortWorks Heating & Air",
     "44388", "125- Columbia",
     [("Sarah Jenkins", "Owner"), ("Luis Romero", "Technician"), ("Pete Aldridge", "Technician")]),
    ("columbia-fit-2026-06-17", "info@duckriverair.example", "Duck River Air",
     "46233", "125- Columbia",
     [("Hank Posey", "Technician")]),
    ("murfreesboro-ductless-2026-07-15", "jturner@turnermech.example", "Turner Mechanical",
     "45102", "107- Murfreesboro",
     [("James Turner", "Owner"), ("Cody Banks", "Technician")]),
    ("murfreesboro-ductless-2026-07-15", "dispatch@midtncooling.example", "Mid-TN Cooling",
     "45990", "107- Murfreesboro",
     [("Angela Wu", "Inside Sales"), ("Ray Holcomb", "Technician"), ("Trent Mabry", "Technician")]),
]


def _ask_date(prompt):
    raw = input(prompt).strip()
    if not raw:
        return date.today()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        print("  ! use YYYY-MM-DD — falling back to today")
        return date.today()


def seed_demo(repo):
    repo.init()
    if repo.all_registrations_flat():
        print("DB already has registrations — not seeding on top of real data.")
        return
    for event_id, email, company, account, branch, attendees in DEMO_REGS:
        reg = build_registration({
            "event_id": event_id, "contact_email": email, "company_name": company,
            "account_number": account, "branch": branch,
            "attendees_list": [{"name": n, "role": r} for n, r in attendees],
        })
        out = repo.save_registration(reg)
        print(f"  + reg {out['registration_id']:04d}  {company}  -> {event_id}")
    write_registrations_xlsx(repo)
    print(f"Seeded {len(DEMO_REGS)} demo registrations (mirrored to registrations.xlsx).")


def do_generate():
    jobs = generate_emails()
    if not jobs:
        print("No upcoming-class registrations found — seed demo data first (option 5).")
        return
    regs = sorted({j["reg_id"] for j in jobs})
    print(f"Generated {len(jobs)} emails + {len(regs)} .ics invites "
          f"for {len(regs)} students -> {EMAIL_OUT_DIR}")
    print(f"Full plan: {CAMPAIGN_SCHEDULE_XLSX}")
    for j in sorted(jobs, key=lambda j: (j["send_on"], j["reg_id"])):
        print(f"  {j['send_on']}  [{j['stage']}-day]  reg {j['reg_id']:04d}  "
              f"{j['reg']['contact_email']:<34}  {j['view']['topic']}")


def do_send():
    today = _ask_date("Simulate today as YYYY-MM-DD (enter = real today): ")
    sent = run_sender(today)
    if not sent:
        print(f"Nothing due as of {today}. (Already sent, or send dates are in the future.)")
        return
    print(f"\"Sent\" {len(sent)} email(s) as of {today} -> {CAMPAIGN_OUTBOX_XLSX}")
    for j in sent:
        print(f"  -> [{j['stage']}-day]  reg {j['reg_id']:04d}  {j['reg']['contact_email']:<34} "
              f"class {j['class_date']}  ({j['status'].split(' — ')[0]})")


def do_status():
    jobs = upcoming_jobs()
    done = sent_keys()
    if not jobs and not done:
        print("Nothing planned and nothing sent. Run 5) seed, then 1) generate.")
        return
    print(f"Planned emails (upcoming classes): {len(jobs)}   |   Sent (outbox rows): {len(done)}")
    for j in sorted(jobs, key=lambda j: (j["send_on"], j["reg_id"])):
        mark = "SENT" if (j["reg_id"], j["stage"]) in done else "    "
        print(f"  [{mark}]  send {j['send_on']}  [{j['stage']}-day]  reg {j['reg_id']:04d}  "
              f"{j['reg']['company_name']:<28}  class {j['class_date']}")
    pending = due_jobs()
    if pending:
        print(f"Due right now (real today): {len(pending)} — run option 2.")


def do_preview():
    files = sorted(EMAIL_OUT_DIR.glob("*.html")) if EMAIL_OUT_DIR.exists() else []
    if not files:
        print("No generated emails yet — run option 1 first.")
        return
    for i, f in enumerate(files, 1):
        print(f"  {i}) {f.name}")
    raw = input("Open which one? ").strip()
    if raw.isdigit() and 1 <= int(raw) <= len(files):
        webbrowser.open(files[int(raw) - 1].as_uri())
    else:
        print("  ! not a valid number")


MENU = """
=== M&A Training — Email Campaign demo ===
 1) Generate reminder emails  (HTML + .ics per student -> data/email_campaign/emails/)
 2) Run the sender            (simulated: due emails -> outbox.xlsx)
 3) Campaign status           (planned vs sent)
 4) Preview an email in the browser
 5) Seed demo registrations   (only when the DB is empty)
 0) Exit
"""


def cron_send():
    """The one-shot a scheduler runs daily: regenerate (picks up any new
    registrations / date changes in events.xlsx), then send what's due today.
    Idempotent — the outbox ledger makes re-runs and missed days safe."""
    generate_emails()
    sent = run_sender()
    print(f"{date.today()}: {len(sent)} email(s) sent" if sent
          else f"{date.today()}: nothing due")
    for j in sent:
        print(f"  -> [{j['stage']}-day] reg {j['reg_id']:04d} {j['reg']['contact_email']}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "send":
        cron_send()
        return
    repo = get_repository()
    repo.init()
    if not repo.all_registrations_flat():
        print("Heads-up: the DB has no registrations yet — start with option 5.")
    while True:
        print(MENU)
        choice = input("> ").strip()
        if choice == "1":
            do_generate()
        elif choice == "2":
            do_send()
        elif choice == "3":
            do_status()
        elif choice == "4":
            do_preview()
        elif choice == "5":
            seed_demo(repo)
        elif choice in ("0", "q", ""):
            break
        else:
            print("  ! pick 0-5")


if __name__ == "__main__":
    main()
