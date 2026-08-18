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

# Everything that is read or written at runtime lives under DATA. Point
# APP_DATA_DIR at a mounted volume on a host with an ephemeral filesystem
# (Railway et al) and the DB, the Excel mirror, the catalog, the fliers and the
# email ledger all persist across deploys together. Also what lets a test run
# against a scratch copy instead of the real thing.
DATA = Path(os.environ.get("APP_DATA_DIR") or (HERE / "data")).expanduser()

# Which catalog to serve. Override for a temp test, e.g.
#   EVENTS_XLSX=data/events_june_test.xlsx python3 server.py
_env_events = os.environ.get("EVENTS_XLSX")
EVENTS_XLSX = (Path(_env_events) if _env_events and Path(_env_events).is_absolute()
               else HERE / _env_events if _env_events
               else DATA / "OFFICIAL_CLASS_SCHEDULE.xlsx")

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
# Both env-driven so moving to the client's own domain later is a config change,
# not a code change — nothing here is tied to a particular mail provider.
EMAIL_FROM = os.environ.get("EMAIL_FROM", "traininghubcai@gmail.com")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "M&A Supply Training")

# Gmail SMTP. The password is a 16-character Google App Password, NOT the
# account password — it needs 2-Step Verification switched on for the account.
# Everything here comes from the environment: no credential is ever committed.
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", EMAIL_FROM)
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", EMAIL_FROM)

# The master switch. Deploying this code does NOT start sending — mail only
# leaves the machine when EMAIL_SEND_ENABLED is explicitly turned on, so a
# push can never surprise a dealer with a duplicate reminder.
EMAIL_SEND_ENABLED = os.environ.get("EMAIL_SEND_ENABLED", "").strip().lower() \
    in ("1", "true", "yes", "on")
# Gmail throttles bursts harder than it throttles volume. One second between
# messages keeps a full day's batch comfortably under its rate limits.
EMAIL_SEND_PAUSE = float(os.environ.get("EMAIL_SEND_PAUSE", "1.0"))

# --- form / display tunables -------------------------------------------------
ROLES = ["Technician", "Inside Sales", "Outside Sales", "Owner"]  # mirror static/app.js
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Territory Manager is left blank by default: John's real data shows one branch
# mapping to several TMs, so it can't be derived from branch. Flip to True only
# if the branches sheet ever holds a real 1:1 branch -> TM mapping.
FILL_TM_FROM_BRANCH = False
