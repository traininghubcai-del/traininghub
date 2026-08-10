"""ONE command to reset EVERYTHING to a clean state derived from the MASTER workbook.

Run this whenever the MASTER changes, or when anything looks out of sync. It rebuilds
every runtime file from `_data_in/MASTER COPY  Training Hub Info Phase 1.xlsx` and wipes
registrations back to zero, so there is never drift between the catalog and the DB/exports.

Order (each step depends on the previous):
  1. build_from_master.py   MASTER -> OFFICIAL_CLASS_SCHEDULE.xlsx + dealers.xlsx + employees.xlsx + classes_sim.csv
  2. make_codes.py          -> tm_keys.yaml + trainer_codes.yaml + access_codes.xlsx + dealers_sim.csv
  3. WIPE registrations DB   registrations / attendees / companies / people / events-cache / logs -> 0
  4. write_registrations.xlsx  regenerate the (now empty) Excel mirror
  5. sync_chat_from_db.py    chat training history -> 0 (real, until real signups)
  6. chat_rag.build_index    rebuild chat indexes

A backup of the DB is written to _archive_data/ before the wipe.

Run:  ./.venv/bin/python tools/reset_all.py
"""
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable
sys.path.insert(0, str(REPO))
import config  # noqa: E402


def run(desc, args, cwd=REPO):
    print(f"\n=== {desc} ===")
    r = subprocess.run([PY, *args], cwd=cwd)
    if r.returncode != 0:
        sys.exit(f"FAILED: {desc}")


def wipe_db():
    print("\n=== 3. wipe registrations DB -> zero ===")
    bak = REPO / "_archive_data" / "reset_backups"
    bak.mkdir(parents=True, exist_ok=True)
    shutil.copy(config.DB_PATH, bak / "registrations.pre_reset.db")
    con = sqlite3.connect(config.DB_PATH)
    con.execute("PRAGMA foreign_keys=OFF")
    for t in ["registration_attendees", "registrations", "companies", "people",
              "events", "class_log", "nudge_log", "email_change_requests"]:
        con.execute(f"DELETE FROM {t}")
    con.commit()
    con.execute("VACUUM")
    con.commit()
    con.close()
    print("  DB wiped (backup -> _archive_data/reset_backups/registrations.pre_reset.db)")


def regen_xlsx():
    print("\n=== 4. regenerate registrations.xlsx (empty mirror) ===")
    from src.db import get_repository
    from src.export import write_registrations_xlsx
    write_registrations_xlsx(get_repository())
    print("  registrations.xlsx refreshed from empty DB")


def main():
    run("1. build runtime files from MASTER", ["tools/build_from_master.py"])
    run("2. regenerate real keys (make_codes)", ["tools/make_codes.py"])
    wipe_db()
    regen_xlsx()
    run("5. reset chat history to real zero", ["tools/sync_chat_from_db.py"])
    run("6. rebuild chat indexes", ["-m", "chat_rag.build_index"], cwd=REPO / "chat_bot")
    print("\n✅ FULL RESET COMPLETE — everything derives from the MASTER, registrations at zero.")
    print("   Restart the server to pick it all up:  ./.venv/bin/python server.py")


if __name__ == "__main__":
    main()
