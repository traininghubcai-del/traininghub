"""Single source of truth for paths, the export-column contract, and tunables.

Every module imports from here instead of hard-coding paths or constants. When
the app is migrated off SQLite, only DB_BACKEND / DB_PATH change.
"""
import os
import re
from pathlib import Path

# --- paths -------------------------------------------------------------------
HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
DATA = HERE / "data"

# Which catalog to serve. Override for a temp test, e.g.
#   EVENTS_XLSX=data/events_june_test.xlsx python3 server.py
_env_events = os.environ.get("EVENTS_XLSX")
EVENTS_XLSX = (Path(_env_events) if _env_events and Path(_env_events).is_absolute()
               else HERE / (_env_events or "data/OFFICIAL_CLASS_SCHEDULE.xlsx"))

# Real program-dealer directory (Customer ID, Customer Name, Sales Rep). The form
# offers these names as a typeahead; account # and TM are resolved server-side so
# the dealer never has to know their account number.
DEALERS_XLSX = DATA / "dealers.xlsx"

DB_PATH = DATA / "registrations.db"
# Live Excel mirror of the DB, rewritten after every submit so John can just open
# the file (no export step). The DB stays the safe write target; this is a copy.
REG_XLSX = DATA / "registrations.xlsx"

# Backend selector for the repository layer. Swap to "postgres" once a
# postgres_repo is added — app code never changes, only this line.
DB_BACKEND = os.environ.get("DB_BACKEND", "sqlite")

# --- export contract ---------------------------------------------------------
# Registration columns, EXACTLY matching John's sheet (display header, internal
# name). Territory Manager is stored blank and filled in later by M&A.
COLUMNS = [
    ("date_info",          "date_info"),
    ("Contact Email",      "contact_email"),
    ("Company Name",       "company_name"),
    ("Account Number",     "account_number"),
    ("# Attending",        "num_attending"),
    ("Names of Attendees", "attendees"),
    ("Branch Location:",   "branch"),
    ("Territory Manager",  "territory_manager"),
]

# --- email campaign ------------------------------------------------------------
# Everything the campaign produces lives under data/email_campaign/ (generated,
# git-ignored). The sender is simulated until a mail provider is wired in:
# "sending" = appending the email's row to OUTBOX_XLSX so it can be demoed.
EMAIL_CAMPAIGN_DIR = DATA / "email_campaign"
EMAIL_OUT_DIR = EMAIL_CAMPAIGN_DIR / "emails"
CAMPAIGN_SCHEDULE_XLSX = EMAIL_CAMPAIGN_DIR / "campaign_schedule.xlsx"
CAMPAIGN_OUTBOX_XLSX = EMAIL_CAMPAIGN_DIR / "outbox.xlsx"
REMINDER_DAYS = [7, 3, 1]            # days before class -> one reminder email each
EMAIL_FROM = "traininghubcai@gmail.com"  # sends are still simulated until SMTP is wired

# --- form / display tunables -------------------------------------------------
ROLES = ["Technician", "Inside Sales", "Outside Sales", "Owner"]  # mirror static/app.js
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Territory Manager is left blank by default: John's real data shows one branch
# mapping to several TMs, so it can't be derived from branch. Flip to True only
# if the branches sheet ever holds a real 1:1 branch -> TM mapping.
FILL_TM_FROM_BRANCH = False
