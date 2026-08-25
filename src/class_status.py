"""Where a class sits, right now — computed, never stored.

ONE ledger, one derivation. The catalog holds the date and whether the class is
cancelled; the registrations DB holds who signed up and who got graded. Nothing
anywhere holds the word "OPEN" or "GRADED", because those are answers to "what
time is it?" and they would be wrong by the next midnight.

That is also what archiving means here. There is no archive table and no
archived flag — a class is archived when it is finished AND settled, which this
function works out from the same two facts. Fix a class's date to a future day
and it leaves the archive on the very next response; nobody has to remember to
un-archive it. Cancel it and it lands there immediately. The ledger is the only
truth and the labels are just how it reads today.

    STATUS          WHEN
    BAD DATE        the date cannot be read at all — somebody must fix it
    ERASED          cancelled (active=false) — whatever its date
    NOT-GRADED      finished, people signed up, someone is still ungraded
    GRADED          finished, people signed up, everyone graded
    NO SIGNUPS      finished, nobody ever registered — say so plainly
    TODAY           running today
    TOMORROW        running tomorrow
    OPEN            further out than tomorrow
"""
from datetime import date, timedelta

BAD_DATE = "BAD DATE"
ERASED = "ERASED"
NOT_GRADED = "NOT-GRADED"
GRADED = "GRADED"
NO_SIGNUPS = "NO SIGNUPS"
TODAY = "TODAY"
TOMORROW = "TOMORROW"
OPEN = "OPEN"

# The whole vocabulary. This is a CHECKLIST, not a sort order — the class list
# is sorted strictly by date (see hub_modes.classes_overview). Ranking rows by
# status re-arranged the calendar behind the reader's back, which is exactly
# what a schedule must never do; status earns a column, not the ordering.
ORDER = [BAD_DATE, TODAY, TOMORROW, OPEN, NOT_GRADED, GRADED, NO_SIGNUPS, ERASED]

# Three buckets over those seven. This is the archive.
LIVE = "live"          # still going to happen — the dealer-facing half
ACTION = "action"      # finished and someone has to do something about it
ARCHIVE = "archive"    # finished and settled, or cancelled — nothing owed

LIFECYCLE = {
    TODAY: LIVE, TOMORROW: LIVE, OPEN: LIVE,
    # a broken date is work for a human, so it lands in the same bucket as an
    # ungraded class rather than being filed away as settled
    BAD_DATE: ACTION,
    NOT_GRADED: ACTION,
    GRADED: ARCHIVE, NO_SIGNUPS: ARCHIVE, ERASED: ARCHIVE,
}

# The FSR-Audit column: the same truth as STATUS, flattened to the only three
# answers an auditor asks — is a grade owed on this class, is it done, or is it
# not a grading question yet. Derived from the label so the two columns cannot
# contradict each other; if one is ever wrong they are both wrong, which is the
# point of computing them here rather than in two places.
AUDIT_NEEDED = "needs grading"
AUDIT_DONE = "graded"
AUDIT_NA = "NA"

AUDIT = {
    NOT_GRADED: AUDIT_NEEDED,
    GRADED: AUDIT_DONE,
    # future, today, a finished class nobody signed up for, and a cancelled one
    # are all "nothing to audit" — no grade is owed and none is missing
    OPEN: AUDIT_NA, TODAY: AUDIT_NA, TOMORROW: AUDIT_NA,
    NO_SIGNUPS: AUDIT_NA, ERASED: AUDIT_NA, BAD_DATE: AUDIT_NA,
}

AUDIT_CSS = {AUDIT_NEEDED: "au-needed", AUDIT_DONE: "au-done", AUDIT_NA: "au-na"}


def audit_label(status):
    """'needs grading' | 'graded' | 'NA' for a status label."""
    return AUDIT.get(status, AUDIT_NA)


# CSS class per label — the pill's look is decided here so the list, the class
# page and any future screen cannot drift apart on colour.
CSS = {
    OPEN: "st-open", TODAY: "st-today", TOMORROW: "st-tomorrow",
    NOT_GRADED: "st-notgraded", GRADED: "st-graded",
    NO_SIGNUPS: "st-nosignups", ERASED: "st-erased",
    BAD_DATE: "st-baddate",
}


def today():
    """Same clock as everything else that splits past from upcoming."""
    from datetime import datetime
    return datetime.now().date()


def status_label(event_date, *, active=True, registered=0, graded_count=0, now=None):
    """The one label for this class. See the table in the module docstring.

    event_date is an ISO string (or a date); anything unreadable is treated as
    the far future, because a class we can't date is certainly not finished.
    """
    if not active:
        return ERASED                      # a cancelled class is cancelled, full stop

    now = now or today()
    d = _as_date(event_date)
    if d is None:
        # NEVER OPEN. "I can't read this date" and "this class is coming up"
        # are opposite claims, and guessing the friendlier one is how a
        # finished class ends up advertising itself as upcoming.
        return BAD_DATE

    if d < now:
        if not registered:
            return NO_SIGNUPS              # it happened and nobody ever signed up
        return GRADED if graded_count >= registered else NOT_GRADED
    if d == now:
        return TODAY
    if d == now + timedelta(days=1):
        return TOMORROW
    return OPEN


def describe(event_date, *, active=True, registered=0, graded_count=0, now=None):
    """{status, lifecycle, css, timing, fsr_audit} — what every API row carries."""
    label = status_label(event_date, active=active, registered=registered,
                         graded_count=graded_count, now=now)
    now = now or today()
    d = _as_date(event_date)
    # an unreadable date is not "upcoming" either — it is nothing, and nothing
    # downstream should treat it as a class that has yet to happen
    timing = ("unknown" if d is None else
              "past" if d < now else "today" if d == now else "upcoming")
    audit = audit_label(label)
    return {"status": label, "lifecycle": LIFECYCLE[label],
            "status_css": CSS[label], "timing": timing,
            "fsr_audit": audit, "fsr_audit_css": AUDIT_CSS[audit]}


def _as_date(value):
    """date, or None when it genuinely cannot be read.

    The [:10] is deliberate: openpyxl hands back '2026-09-01 00:00:00' for a
    real date cell, and that is a perfectly good date, not a broken one.
    """
    from datetime import datetime
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value or "").strip()[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
