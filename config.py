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
# git-ignored). Mail goes out through the Brevo SMTP relay; every send, real or
# simulated, appends its row to OUTBOX_XLSX, which is the dedupe ledger as well
# as the audit trail. See docs/RULE-email-sending.md.
EMAIL_CAMPAIGN_DIR = DATA / "email_campaign"
EMAIL_OUT_DIR = EMAIL_CAMPAIGN_DIR / "emails"
CAMPAIGN_SCHEDULE_XLSX = EMAIL_CAMPAIGN_DIR / "campaign_schedule.xlsx"
CAMPAIGN_OUTBOX_XLSX = EMAIL_CAMPAIGN_DIR / "outbox.xlsx"
REMINDER_DAYS = [7, 3, 1]            # days before class -> one reminder email each
# Both env-driven so moving to the client's own domain later is a config change,
# not a code change — nothing here is tied to a particular mail provider.
EMAIL_FROM = os.environ.get("EMAIL_FROM", "traininghubcai@gmail.com")
EMAIL_FROM_NAME = os.environ.get("EMAIL_FROM_NAME", "M&A Supply Training")

# Brevo SMTP relay. Everything comes from the environment: no credential is
# ever committed.
#
# Three fields, and the two easy ones are the ones people get wrong:
#   SMTP_USER     The Brevo *SMTP login*, from Brevo -> SMTP & API -> SMTP.
#                 It is NOT the address mail is sent from — Brevo issues its own
#                 login, usually like "9a1b2c001@smtp-brevo.com". Sending the
#                 account's Gmail address here fails with 535 Authentication
#                 failed, which reads like a bad password and is not one.
#   SMTP_PASSWORD The Brevo SMTP key ("xsmtpsib-..."), from the same page. This
#                 is a different credential from a Brevo API key ("xkeysib-...");
#                 the two are not interchangeable in either direction.
#   EMAIL_FROM    Must be a sender Brevo has verified, or it rejects the message
#                 after a successful login. Add and confirm it under Senders.
#
# Left as a default so no fallback can quietly point a Brevo key at the wrong
# host: a mismatch here is the difference between "sent" and 535.
# Brevo's HTTP API, and the reason it is the default transport rather than a
# fallback: Railway blocks outbound SMTP on every port, so a correct SMTP setup
# times out there with no error a person could act on. The API is plain HTTPS on
# 443, which nothing blocks. Set BREVO_API_KEY to an API key ("xkeysib-...")
# from Brevo -> SMTP & API -> API keys, and SMTP is not used at all.
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "").strip()
BREVO_API_URL = os.environ.get("BREVO_API_URL", "https://api.brevo.com/v3/smtp/email")

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp-relay.brevo.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
# No fallback to EMAIL_FROM on purpose. That default was right for Gmail, where
# login and sender are the same address, and is wrong for every relay that
# issues its own login — it turns a missing setting into a confusing auth error
# instead of a clear "SMTP_USER is not set".
SMTP_USER = os.environ.get("SMTP_USER", "").strip()
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "").strip()
EMAIL_REPLY_TO = os.environ.get("EMAIL_REPLY_TO", EMAIL_FROM)
# 587 speaks STARTTLS, 465 is TLS from the first byte. Derived from the port so
# switching ports is one variable, not two, and overridable for an odd relay.
SMTP_SSL = os.environ.get("SMTP_SSL", "").strip().lower() in ("1", "true", "yes", "on") \
    or SMTP_PORT == 465

# The master switch. Deploying this code does NOT start sending — mail only
# leaves the machine when EMAIL_SEND_ENABLED is explicitly turned on, so a
# push can never surprise a dealer with a duplicate reminder.
EMAIL_SEND_ENABLED = os.environ.get("EMAIL_SEND_ENABLED", "").strip().lower() \
    in ("1", "true", "yes", "on")
# Relays throttle bursts harder than they throttle volume. One second between
# messages keeps a full day's batch comfortably under Brevo's rate limits.
EMAIL_SEND_PAUSE = float(os.environ.get("EMAIL_SEND_PAUSE", "1.0"))

# The daily reminder run, inside the web process (see src/scheduler.py). Off by
# default and separate from EMAIL_SEND_ENABLED on purpose: one says mail may
# leave the machine, this says the machine may decide on its own when to send.
# Turning only the first on leaves the Admin "send reminders" button working and
# the 7/3/1-day schedule dormant, which is the right state to deploy into first.
EMAIL_DAILY_SEND = os.environ.get("EMAIL_DAILY_SEND", "").strip().lower() \
    in ("1", "true", "yes", "on")
# Hour of the local day the run happens, 0-23. Containers are UTC unless told
# otherwise, so set TZ=America/Chicago alongside this or 8 means 3am for John.
EMAIL_SEND_HOUR = int(os.environ.get("EMAIL_SEND_HOUR", "8"))

# --- form / display tunables -------------------------------------------------
ROLES = ["Technician", "Inside Sales", "Outside Sales", "Owner"]  # mirror static/app.js
MONTHS = ["January", "February", "March", "April", "May", "June",
          "July", "August", "September", "October", "November", "December"]
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Territory Manager is left blank by default: John's real data shows one branch
# mapping to several TMs, so it can't be derived from branch. Flip to True only
# if the branches sheet ever holds a real 1:1 branch -> TM mapping.
FILL_TM_FROM_BRANCH = False
