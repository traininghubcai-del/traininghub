"""Schedule guards — the only place that decides whether a date/time may be written.

A class date is not free text. Once a class is in the past the whole app changes
behaviour around it: dealers stop seeing it (`catalog.public_events`), the FSR
grade sheet unlocks (`hub_modes.class_status` -> can_grade), and it drops to the
bottom of the control panel. All of that reads the date and behaves correctly —
which is exactly why a bad date is so damaging: nothing downstream complains, it
just quietly reclassifies a live class as finished.

So the refusal has to live on the WRITE side, and it lives here so create and
edit cannot drift apart. `src.manage` calls these before it touches a cell; the
browser repeats the same rules as a courtesy, never as the check.
"""
import re
from datetime import date, datetime, time

# "Today" is the local machine's calendar day — the SAME clock every other
# past/upcoming decision in the app uses (catalog.list_events, hub_modes.
# class_status, manage.list_classes all compare against datetime.now().date()).
# Change it here and you MUST change it there, or a class can be past for the
# dealer feed and still editable into the past by an admin.
def today():
    return datetime.now().date()


# Locked wording — the API and the browser say the identical thing.
ERR_BAD_DATE = "Date must be YYYY-MM-DD."
ERR_PAST_DATE = "Can't set the class date to a day that already passed."
ERR_END_BEFORE_START = "End time must be after start time."
ERR_BAD_TIME = "{label} time must be a time like 09:00 or 1:30 PM."

_CLOCK_RE = re.compile(r"^(\d{1,2})(?::(\d{2}))?(?::\d{2})?\s*([AaPp])?\.?[Mm]?\.?$")


def is_blank(raw):
    """A blank time is 'TBD', not an error — the catalog ships classes that way."""
    return raw is None or str(raw).strip() == ""


def parse_event_date(raw):
    """'2026-09-01' (or a real date/datetime cell) -> date. None when unreadable.

    Deliberately strict on strings: YYYY-MM-DD only. Anything looser and
    '09/01/26' silently becomes a date nobody meant.
    """
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw or "").strip()[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def refuse_past_date(d):
    """Error message when this date has already gone by, else None.

    Today is allowed on purpose: a class running right now is still editable,
    and that is the day an FSR is standing in the room with the roster open.
    """
    if not isinstance(d, date):
        return ERR_BAD_DATE
    return ERR_PAST_DATE if d < today() else None


def parse_clock(raw):
    """A written time -> (hour, minute). None when it can't be read.

    Accepts everything the catalog has ever held: '09:00', '9:00', a real Excel
    time cell, '09:00:00', and the 12-hour forms a person types by hand
    ('9 AM', '1:30pm').
    """
    if isinstance(raw, datetime):
        return raw.hour, raw.minute
    if isinstance(raw, time):
        return raw.hour, raw.minute
    m = _CLOCK_RE.match(str(raw or "").strip())
    if not m:
        return None
    h, mins, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap:
        if not 1 <= h <= 12:
            return None
        h = (h % 12) + (12 if ap == "p" else 0)
    if not (0 <= h <= 23 and 0 <= mins <= 59):
        return None
    return h, mins


def to_hhmm(raw):
    """Normalised '09:00' for storage, or '' when blank/unreadable.

    Everything downstream (to_12h, to_compact, build_date_info) matches on
    HH:MM, so a hand-typed '9 AM' has to land in the sheet as '09:00' or the
    class renders its time as raw text.
    """
    hm = parse_clock(raw)
    return "" if hm is None else f"{hm[0]:02d}:{hm[1]:02d}"


def refuse_bad_times(start, end):
    """Error message for the start/end pair, else None.

    Blank stays legal (a class with no time yet shows 'Time TBD' and is flagged
    by catalog.missing_info). But anything actually written must be readable,
    and a pair must run forwards.
    """
    s_blank, e_blank = is_blank(start), is_blank(end)
    s = None if s_blank else parse_clock(start)
    e = None if e_blank else parse_clock(end)
    if not s_blank and s is None:
        return ERR_BAD_TIME.format(label="Start")
    if not e_blank and e is None:
        return ERR_BAD_TIME.format(label="End")
    if s and e and (e[0] * 60 + e[1]) <= (s[0] * 60 + s[1]):
        return ERR_END_BEFORE_START
    return None


def refuse_bad_schedule(date_raw, start, end, require_date=True):
    """One call for 'is this a legal class slot?' — used by create and by edit.

    Returns an error message or None. date_raw may be omitted (require_date
    False) when the caller is patching times on a class whose date isn't moving.
    """
    if require_date or not is_blank(date_raw):
        d = parse_event_date(date_raw)
        if d is None:
            return ERR_BAD_DATE
        err = refuse_past_date(d)
        if err:
            return err
    return refuse_bad_times(start, end)
