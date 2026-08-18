"""Email campaign: per-student reminder emails 7 / 3 / 1 days before class.

Pipeline (all local — no mail provider yet):
  1. ``generate_emails()`` — for every registration with an upcoming class,
     render one branded HTML email per reminder stage (7/3/1 days out, same
     design language as the landing page) plus an ``.ics`` calendar invite,
     into ``data/email_campaign/emails/``. File names start with the
     registration id. The full plan is written to ``campaign_schedule.xlsx``.
  2. ``run_sender(today)`` — finds the stage emails due on ``today`` (or
     overdue and never sent) and "sends" them. Today that means appending one
     row per email to ``outbox.xlsx`` so every send can be inspected/demoed.
     When a provider is chosen, only ``_deliver()`` changes — the schedule and
     dedupe logic stay exactly as they are.

Reads the same sources as the app: the SQLite repo (registrations) and
events.xlsx via src.catalog. Writes only inside data/email_campaign/.
"""
import smtplib
import time
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr
from urllib.parse import quote

from openpyxl import Workbook, load_workbook

from config import (CAMPAIGN_OUTBOX_XLSX, CAMPAIGN_SCHEDULE_XLSX, EMAIL_FROM,
                    EMAIL_FROM_NAME, EMAIL_OUT_DIR, EMAIL_REPLY_TO,
                    EMAIL_SEND_ENABLED, EMAIL_SEND_PAUSE, REMINDER_DAYS,
                    SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USER)
from src.catalog import event_view, is_active, load_catalog
from src.db import get_repository

# --- the three reminder stages -------------------------------------------------
# Same email skeleton, different urgency. `accent` colors the countdown chip.
STAGES = {
    7: {
        "eyebrow": "ONE WEEK OUT",
        "chip": "7 DAYS TO GO",
        "headline": "YOUR CLASS IS IN 7 DAYS",
        "lead": ("Your team's seats are confirmed. Lock the date in now — "
                 "one tap below adds the class to your calendar."),
        "accent": "#1d6fc2",
    },
    3: {
        "eyebrow": "GETTING CLOSE",
        "chip": "3 DAYS TO GO",
        "headline": "3 DAYS UNTIL YOUR CLASS",
        "lead": ("Quick reminder — here are your class details and the team "
                 "you registered. Reply to this email if anything changed."),
        "accent": "#e0a92b",
    },
    1: {
        "eyebrow": "TOMORROW",
        "chip": "TOMORROW",
        "headline": "1 DAY — BE PREPARED!",
        "lead": ("Your class is tomorrow. Run through the checklist below so "
                 "your team gets the most out of the day."),
        "accent": "#1f8a4c",
    },
}

SCHEDULE_COLUMNS = ["reg_id", "contact_email", "company_name", "event_id", "topic",
                    "class_date", "stage_days", "send_on", "subject",
                    "html_file", "ics_file"]
OUTBOX_COLUMNS = ["sent_at", "simulated_today", "stage_days", "send_on", "reg_id",
                  "contact_email", "company_name", "event_id", "topic",
                  "class_date", "subject", "html_file", "status"]


def _subject(stage, view):
    if stage == 1:
        return f"Tomorrow: {view['topic']} — be prepared!"
    return f"{stage} days to go: {view['topic']} — {view['date_display']}"


# --- recipients ------------------------------------------------------------------

def upcoming_jobs(today=None):
    """One job per (registration x stage) for classes on/after `today`.

    Joins the repo's flat registrations to the live events.xlsx catalog, so a
    date change in Excel automatically reschedules every reminder.
    """
    today = today or date.today()
    events, _, _ = load_catalog()
    jobs = []
    for reg in get_repository().all_registrations_flat():
        ev = events.get(reg["event_id"])
        if not ev or not is_active(ev):
            continue
        view = event_view(ev)
        class_date = datetime.strptime(str(ev["event_date"]), "%Y-%m-%d").date()
        if class_date < today:
            continue  # class already happened — nothing left to remind
        reg_id = int(reg.get("id") or reg.get("reg_id") or 0)
        for stage in REMINDER_DAYS:
            jobs.append({
                "reg_id": reg_id,
                "reg": reg,
                "event": ev,
                "view": view,
                "class_date": class_date,
                "stage": stage,
                "send_on": class_date - timedelta(days=stage),
                "subject": _subject(stage, view),
                "html_name": f"{reg_id:04d}_{stage}day.html",
                "ics_name": f"{reg_id:04d}_invite.ics",
            })
    return jobs


# --- calendar (the "add to calendar" button) -------------------------------------

def _dt_compact(ev, key):
    """'2026-06-17' + '09:00' -> '20260617T090000' (floating local time)."""
    d = str(ev["event_date"]).replace("-", "")
    t = str(ev[key]).replace(":", "")
    return f"{d}T{t}00"


def google_calendar_url(ev, view):
    details = f"{view['host_label']}\nRegistered via the M&A Supply Training Hub."
    return ("https://calendar.google.com/calendar/render?action=TEMPLATE"
            f"&text={quote(view['topic'] + ' — M&A Supply Training')}"
            f"&dates={_dt_compact(ev, 'start_time')}/{_dt_compact(ev, 'end_time')}"
            f"&location={quote(view['event_location'])}"
            f"&details={quote(details)}")


def ics_text(ev, view, reg_id):
    """Minimal .ics invite (floating local time — fine for a same-state class)."""
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    return "\r\n".join([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//M&A Supply//Training Hub//EN",
        "BEGIN:VEVENT",
        f"UID:reg-{reg_id}-{ev['event_id']}@ma-supply-training",
        f"DTSTAMP:{stamp}",
        f"DTSTART:{_dt_compact(ev, 'start_time')}",
        f"DTEND:{_dt_compact(ev, 'end_time')}",
        f"SUMMARY:{view['topic']} — M&A Supply Training",
        f"LOCATION:{view['event_location']}",
        f"DESCRIPTION:{view['host_label']}",
        "END:VEVENT",
        "END:VCALENDAR",
        "",
    ])


# --- HTML rendering (same design language as static/styles.css) -------------------
# Email clients ignore <style> blocks and custom fonts, so this is the site's
# palette re-built as a 600px table with inline styles + system font stacks.

_FONT = "'Saira','Barlow',Arial,Helvetica,sans-serif"


def _btn(href, label, solid=True):
    style = (f"background:#1d6fc2;color:#ffffff;border:2px solid #1d6fc2;" if solid else
             f"background:#ffffff;color:#155a9f;border:2px solid #1d6fc2;")
    return (f'<a href="{href}" style="display:inline-block;{style}'
            f'font-family:{_FONT};font-weight:700;font-size:14px;letter-spacing:.02em;'
            f'text-decoration:none;padding:13px 26px;margin:4px 6px;">{label}</a>')


def _detail_row(label, value):
    return (f'<tr><td style="padding:7px 0;font-family:{_FONT};font-weight:600;'
            f'font-size:12px;letter-spacing:.06em;color:#0a2540;text-transform:uppercase;'
            f'width:120px;vertical-align:top;">{label}</td>'
            f'<td style="padding:7px 0;font-family:Barlow,Arial,sans-serif;font-size:15px;'
            f'color:#16222f;">{value}</td></tr>')


def _prep_checklist(view):
    items = [
        "Arrive 15 minutes early — check-in opens before the first session.",
        "Bring a notepad; bring your tools/gauges if your class is hands-on.",
        "Make sure every attendee on your list below knows the time and location.",
    ]
    if view.get("notes"):
        items.insert(0, f"<b>From your branch:</b> {view['notes']}")
    lis = "".join(
        f'<li style="margin:6px 0;color:#6b5212;font-family:Barlow,Arial,sans-serif;'
        f'font-size:14px;">{i}</li>' for i in items)
    return (f'<div style="background:#fff8e6;border-left:4px solid #e0a92b;'
            f'padding:14px 18px;margin:22px 0 4px;">'
            f'<p style="margin:0 0 6px;font-family:{_FONT};font-weight:700;font-size:13px;'
            f'letter-spacing:.08em;color:#6b5212;text-transform:uppercase;">Be prepared</p>'
            f'<ul style="margin:0;padding-left:18px;">{lis}</ul></div>')


def render_email(job):
    """One full HTML email for a (registration x stage) job."""
    reg, view, ev, stage = job["reg"], job["view"], job["event"], job["stage"]
    s = STAGES[stage]
    cal_url = google_calendar_url(ev, view)
    note = (f'<tr><td style="padding:0 28px 6px;">'
            f'<p style="margin:0;padding:10px 14px;background:#fff8e6;'
            f'border-left:4px solid #e0a92b;color:#6b5212;font-family:Barlow,Arial,'
            f'sans-serif;font-size:13px;">{view["notes"]}</p></td></tr>'
            if view.get("notes") and stage != 1 else "")
    prep = (f'<tr><td style="padding:0 28px;">{_prep_checklist(view)}</td></tr>'
            if stage == 1 else "")
    attendees = reg.get("attendees") or "(no attendee names on file)"

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{job['subject']}</title></head>
<body style="margin:0;padding:0;background:#f3f6fa;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f3f6fa;">
<tr><td align="center" style="padding:26px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0"
       style="width:600px;max-width:100%;background:#ffffff;box-shadow:0 10px 30px rgba(10,37,64,.10);">

  <!-- header : navy bar, blue rule (matches .ma-header) -->
  <tr><td style="background:#0a2540;border-bottom:3px solid #1d6fc2;padding:16px 28px;">
    <span style="font-family:{_FONT};font-weight:800;font-size:17px;letter-spacing:.04em;color:#ffffff;">
      M&amp;A SUPPLY CO. <span style="font-weight:500;color:#acc6e3;">— TRAINING</span>
    </span>
  </td></tr>

  <!-- hero : deep navy, eyebrow + countdown (matches .ma-hero) -->
  <tr><td style="background:#06192e;padding:34px 28px 30px;">
    <p style="margin:0 0 12px;font-family:{_FONT};font-weight:700;font-size:11px;
              letter-spacing:.22em;color:#6fb0ee;">{s['eyebrow']}</p>
    <h1 style="margin:0 0 14px;font-family:{_FONT};font-weight:800;font-size:30px;
               line-height:1.05;color:#ffffff;text-transform:uppercase;">{s['headline']}</h1>
    <span style="display:inline-block;background:{s['accent']};color:#ffffff;
                 font-family:{_FONT};font-weight:800;font-size:13px;letter-spacing:.08em;
                 padding:7px 16px;">{s['chip']} &middot; {view['weekday_display'].upper()}, {view['date_display'].upper()}</span>
    <p style="margin:16px 0 0;font-family:Barlow,Arial,sans-serif;font-size:15px;
              line-height:1.55;color:#c7d8e8;">{s['lead']}</p>
  </td></tr>

  <!-- class card : blue left rail (matches .ma-class-banner) -->
  <tr><td style="padding:26px 28px 8px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #d9e2ec;border-left:5px solid #1d6fc2;">
      <tr><td style="padding:18px 20px;">
        <h2 style="margin:0 0 12px;font-family:{_FONT};font-weight:800;font-size:20px;
                   color:#0a2540;text-transform:uppercase;line-height:1.1;">{view['topic']}</h2>
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0">
          {_detail_row("Date", f"{view['weekday_display']}, {view['date_display']}")}
          {_detail_row("Time", view['time_display'])}
          {_detail_row("Location", view['event_location'])}
          {_detail_row("Hosted by", view['host_label'])}
        </table>
      </td></tr>
    </table>
  </td></tr>

  {note}{prep}

  <!-- add to calendar -->
  <tr><td align="center" style="padding:18px 28px 6px;">
    {_btn(cal_url, "&#128197;&nbsp; ADD TO GOOGLE CALENDAR")}
    {_btn("cid:invite.ics", "DOWNLOAD .ICS (OUTLOOK / APPLE)", solid=False)}
    <p style="margin:10px 0 0;font-family:Barlow,Arial,sans-serif;font-size:12px;color:#56697a;">
      The attached <b>invite.ics</b> works with Outlook and Apple Calendar.</p>
  </td></tr>

  <!-- registered team (matches .ma-tag / blue-soft) -->
  <tr><td style="padding:16px 28px 26px;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
           style="background:#e9f1fa;border:1px solid #cfe1f5;">
      <tr><td style="padding:16px 20px;">
        <p style="margin:0 0 8px;font-family:{_FONT};font-weight:700;font-size:12px;
                  letter-spacing:.08em;color:#155a9f;text-transform:uppercase;">
          Your registered team — {reg['company_name']}</p>
        <p style="margin:0;font-family:Barlow,Arial,sans-serif;font-size:14px;color:#16222f;">
          {attendees}</p>
        <p style="margin:8px 0 0;font-family:Barlow,Arial,sans-serif;font-size:12px;color:#56697a;">
          {reg['num_attending']} attending &middot; registered with {reg['contact_email']}
          &middot; reply to this email to make changes.</p>
      </td></tr>
    </table>
  </td></tr>

  <!-- footer (matches .ma-footer) -->
  <tr><td style="background:#06192e;padding:18px 28px;">
    <p style="margin:0;font-family:Barlow,Arial,sans-serif;font-size:12px;color:#b9cadb;">
      M&amp;A Supply Company — Training Hub &middot; Automated class reminder
      ({stage} day{'s' if stage != 1 else ''} before your class).</p>
  </td></tr>

</table>
</td></tr></table>
</body></html>"""


# --- step 1: generate ---------------------------------------------------------------

def generate_emails(today=None):
    """Render every (registration x stage) email + one .ics per registration.

    Returns the job list. Also rewrites campaign_schedule.xlsx — the full plan,
    one row per email, so the campaign can be reviewed in Excel before any send.
    """
    EMAIL_OUT_DIR.mkdir(parents=True, exist_ok=True)
    jobs = upcoming_jobs(today)
    ics_done = set()
    for job in jobs:
        (EMAIL_OUT_DIR / job["html_name"]).write_text(render_email(job), encoding="utf-8")
        if job["reg_id"] not in ics_done:
            (EMAIL_OUT_DIR / job["ics_name"]).write_text(
                ics_text(job["event"], job["view"], job["reg_id"]), encoding="utf-8")
            ics_done.add(job["reg_id"])

    wb = Workbook()
    ws = wb.active
    ws.title = "schedule"
    ws.append(SCHEDULE_COLUMNS)
    for j in sorted(jobs, key=lambda j: (j["send_on"], j["reg_id"], -j["stage"])):
        ws.append([j["reg_id"], j["reg"]["contact_email"], j["reg"]["company_name"],
                   j["view"]["event_id"], j["view"]["topic"], str(j["class_date"]),
                   j["stage"], str(j["send_on"]), j["subject"],
                   f"emails/{j['html_name']}", f"emails/{j['ics_name']}"])
    CAMPAIGN_SCHEDULE_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(CAMPAIGN_SCHEDULE_XLSX)
    return jobs


# --- step 2: send (simulated until a provider is wired) ------------------------------

def _plain_text(job):
    """Text fallback for clients that won't render HTML. Every mail is sent
    multipart/alternative — a text-only reader still gets the what/when/where."""
    v = job["view"]
    return (f"{job['subject']}\n\n"
            f"{v['topic']}\n"
            f"{v.get('weekday', '')} {v.get('event_date', '')}  {v.get('time_display', '')}\n"
            f"{v.get('address_display') or v.get('event_location', '')}\n\n"
            f"Registered under: {job['reg']['company_name']}\n\n"
            "Can't make it? Let your M&A branch know at least 24 hours ahead so "
            "the seat can go to another dealer.\n")


def _deliver(job):
    """Send one reminder through Gmail SMTP, with the .ics attached.

    Returns the string that lands in the outbox `status` column. That string is
    load-bearing: sent_keys() treats a row as "already sent" unless the status
    says it failed, so a bounce or an auth error retries on the next run instead
    of being silently swallowed.

    Nothing leaves the machine unless EMAIL_SEND_ENABLED is on AND a password is
    configured — either missing and this stays a simulation.
    """
    if not EMAIL_SEND_ENABLED:
        return "SIMULATED — written to outbox, no email left this machine"
    if not SMTP_PASSWORD:
        return "FAILED — SMTP_PASSWORD is not set; nothing was sent"

    to = str(job["reg"].get("contact_email", "")).strip()
    if not to:
        return "FAILED — registration has no contact email"

    try:
        msg = EmailMessage()
        msg["Subject"] = job["subject"]
        msg["From"] = formataddr((EMAIL_FROM_NAME, EMAIL_FROM))
        msg["To"] = to
        msg["Reply-To"] = EMAIL_REPLY_TO
        msg.set_content(_plain_text(job))
        msg.add_alternative(render_email(job), subtype="html")
        msg.add_attachment(
            ics_text(job["event"], job["view"], job["reg_id"]).encode("utf-8"),
            maintype="text", subtype="calendar", filename=job["ics_name"])

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as s:
            s.starttls()
            s.login(SMTP_USER, SMTP_PASSWORD)
            s.send_message(msg)
        if EMAIL_SEND_PAUSE > 0:
            time.sleep(EMAIL_SEND_PAUSE)     # stay under Gmail's burst limits
        return f"SENT to {to}"
    except smtplib.SMTPAuthenticationError:
        # Almost always a plain account password instead of an App Password,
        # or 2-Step Verification not enabled on the account.
        return "FAILED — SMTP login rejected (use a Google App Password)"
    except Exception as e:  # noqa: BLE001 - one bad address must not stop the batch
        return f"FAILED — {type(e).__name__}: {e}"


def sent_keys():
    """(reg_id, stage) pairs already sent, from outbox.xlsx — the dedupe ledger.

    A row whose status starts with FAILED does NOT count: that email never
    reached anyone, so the next run should try it again. Anything else (a real
    SENT, or a SIMULATED row from demo mode) counts as done and is never
    re-sent — that is what stops a dealer getting the same reminder twice.
    """
    if not CAMPAIGN_OUTBOX_XLSX.exists():
        return set()
    ws = load_workbook(CAMPAIGN_OUTBOX_XLSX, read_only=True).active
    keys = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        rec = dict(zip(OUTBOX_COLUMNS, row))
        if rec.get("reg_id") is None:
            continue
        if str(rec.get("status") or "").strip().upper().startswith("FAILED"):
            continue
        keys.add((int(rec["reg_id"]), int(rec["stage_days"])))
    return keys


def reminded_today(event_id, today=None):
    """reg_ids that already got a reminder for this class today.

    The (reg, stage) ledger alone can't stop a double-click on the Admin
    "send now" button: the second press skips the stage it just sent and falls
    through to the next one, which is a different key but the same dealer
    getting mail twice in a row. Same-day is the guard that matches what a
    person would call a duplicate.
    """
    today = today or date.today()
    if not CAMPAIGN_OUTBOX_XLSX.exists():
        return set()
    ws = load_workbook(CAMPAIGN_OUTBOX_XLSX, read_only=True).active
    out = set()
    for row in ws.iter_rows(min_row=2, values_only=True):
        rec = dict(zip(OUTBOX_COLUMNS, row))
        if str(rec.get("event_id") or "") != str(event_id):
            continue
        if str(rec.get("status") or "").strip().upper().startswith("FAILED"):
            continue
        if str(rec.get("sent_at") or "")[:10] == str(today):
            out.add(int(rec["reg_id"]))
    return out


def due_jobs(today=None):
    """Emails whose send day arrived (or passed) and were never sent,
    for classes still in the future."""
    today = today or date.today()
    done = sent_keys()
    return [j for j in upcoming_jobs(today)
            if j["send_on"] <= today and (j["reg_id"], j["stage"]) not in done]


def run_sender(today=None):
    """'Send' everything due as of `today`: one outbox.xlsx row per email.

    Re-runnable any day — already-sent (reg, stage) pairs are skipped, so this
    is exactly the function a daily cron/scheduler will call after deploy.
    """
    today = today or date.today()
    return send_jobs(due_jobs(today), today)


def send_jobs(jobs, today=None):
    """Deliver these jobs and append one outbox row each.

    The daily scheduler and the Admin lens "send now" button both come through
    here, so they share one ledger: a reminder sent by hand this afternoon is
    already recorded when tonight's run computes what's due, and the dealer
    never gets it twice.
    """
    today = today or date.today()
    if not jobs:
        return []

    if CAMPAIGN_OUTBOX_XLSX.exists():
        wb = load_workbook(CAMPAIGN_OUTBOX_XLSX)
        ws = wb.active
    else:
        wb = Workbook()
        ws = wb.active
        ws.title = "outbox"
        ws.append(OUTBOX_COLUMNS)

    now = datetime.now().isoformat(timespec="seconds")
    for j in jobs:
        j["status"] = _deliver(j)
        ws.append([now, str(today), j["stage"], str(j["send_on"]), j["reg_id"],
                   j["reg"]["contact_email"], j["reg"]["company_name"],
                   j["view"]["event_id"], j["view"]["topic"], str(j["class_date"]),
                   j["subject"], f"emails/{j['html_name']}", j["status"]])
    CAMPAIGN_OUTBOX_XLSX.parent.mkdir(parents=True, exist_ok=True)
    wb.save(CAMPAIGN_OUTBOX_XLSX)
    return jobs
