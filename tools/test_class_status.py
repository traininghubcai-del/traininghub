"""Proof that class status is derived, not stored — and that the archive moves.

Two things are being tested:

  1. the vocabulary — all seven labels, at their boundaries
  2. the PROPERTY that matters: nothing is written down, so fixing a class's
     date drags it out of the archive on the very next read, and cancelling one
     drops it in. If someone ever adds a stored `status` column, test_archive_*
     is what fails.

    python3 tools/test_class_status.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.class_status import (ACTION, ARCHIVE, AUDIT, LIFECYCLE, LIVE,  # noqa: E402
                              ORDER, audit_label, describe, status_label)

NOW = date(2026, 8, 25)
PASSED, FAILED = [], []


def check(name, got, want):
    ok = got == want
    (PASSED if ok else FAILED).append(name)
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + ("" if ok else f"   got {got!r}, want {want!r}"))


def label(d, **kw):
    return status_label(d, now=NOW, **kw)


def main():
    print(f"today = {NOW}\n")

    print("the seven labels, at their boundaries")
    check("far future            -> OPEN", label("2026-12-01"), "OPEN")
    check("day after tomorrow    -> OPEN", label("2026-08-27"), "OPEN")
    check("tomorrow              -> TOMORROW", label("2026-08-26"), "TOMORROW")
    check("today                 -> TODAY", label("2026-08-25"), "TODAY")
    check("yesterday, 0 signups  -> NO SIGNUPS", label("2026-08-24"), "NO SIGNUPS")
    check("yesterday, 1 of 3 done-> NOT-GRADED",
          label("2026-08-24", registered=3, graded_count=1), "NOT-GRADED")
    check("yesterday, 3 of 3 done-> GRADED",
          label("2026-08-24", registered=3, graded_count=3), "GRADED")
    check("yesterday, 0 of 3 done-> NOT-GRADED",
          label("2026-08-24", registered=3, graded_count=0), "NOT-GRADED")

    print("\ncancelled beats everything — a class you erased is erased")
    check("cancelled + future    -> ERASED", label("2026-12-01", active=False), "ERASED")
    check("cancelled + today     -> ERASED", label("2026-08-25", active=False), "ERASED")
    check("cancelled + graded    -> ERASED",
          label("2026-08-24", active=False, registered=3, graded_count=3), "ERASED")

    print("\nthe archive is the derived bucket, never a stored flag")
    check("OPEN       is live",    describe("2026-12-01", now=NOW)["lifecycle"], LIVE)
    check("TODAY      is live",    describe("2026-08-25", now=NOW)["lifecycle"], LIVE)
    check("NOT-GRADED is action",
          describe("2026-08-24", registered=2, graded_count=0, now=NOW)["lifecycle"], ACTION)
    check("GRADED     is archive",
          describe("2026-08-24", registered=2, graded_count=2, now=NOW)["lifecycle"], ARCHIVE)
    check("NO SIGNUPS is archive", describe("2026-08-24", now=NOW)["lifecycle"], ARCHIVE)
    check("ERASED     is archive",
          describe("2026-12-01", active=False, now=NOW)["lifecycle"], ARCHIVE)

    print("\n...so the archive moves on its own, with nobody un-archiving anything")
    # one class, three moments in its life — same call, no state anywhere
    cls = dict(registered=0, graded_count=0)
    check("test_archive_in_on_time_passing",
          [describe("2026-08-26", now=NOW - timedelta(days=n), **cls)["lifecycle"]
           for n in (2, 1, 0, -1, -2)],
          [LIVE, LIVE, LIVE, LIVE, ARCHIVE])
    # an admin fixes a wrongly-past date to a future one: out of the archive at once
    check("test_archive_out_on_date_fix",
          (describe("2026-08-12", now=NOW, **cls)["lifecycle"],
           describe("2026-09-12", now=NOW, **cls)["lifecycle"]),
          (ARCHIVE, LIVE))
    # grading the last student settles it
    check("test_archive_in_on_last_grade",
          (describe("2026-08-20", registered=2, graded_count=1, now=NOW)["lifecycle"],
           describe("2026-08-20", registered=2, graded_count=2, now=NOW)["lifecycle"]),
          (ACTION, ARCHIVE))
    # cancelling drops it in from wherever it was
    check("test_archive_in_on_cancel",
          (describe("2026-12-01", now=NOW, **cls)["lifecycle"],
           describe("2026-12-01", active=False, now=NOW, **cls)["lifecycle"]),
          (LIVE, ARCHIVE))

    print("\nORDER is the vocabulary, NOT a sort order")
    # The list is sorted strictly by date (hub_modes.classes_overview). Status
    # must never re-arrange the calendar — if this list ever starts driving row
    # order again, August and October end up adjacent and it stops reading as a
    # schedule.
    check("all eight labels accounted for", len(ORDER), 8)
    check("every label has a lifecycle", sorted(ORDER), sorted(LIFECYCLE))
    check("every label has an audit value", sorted(ORDER), sorted(AUDIT))
    check("no duplicates", len(set(ORDER)), len(ORDER))

    print("\nFSR-Audit: three answers, derived from the status label")
    check("past + ungraded  -> needs grading",
          describe("2026-08-24", registered=3, graded_count=1, now=NOW)["fsr_audit"],
          "needs grading")
    check("past + all graded-> graded",
          describe("2026-08-24", registered=3, graded_count=3, now=NOW)["fsr_audit"], "graded")
    check("future           -> NA", describe("2026-09-01", now=NOW)["fsr_audit"], "NA")
    check("today            -> NA", describe("2026-08-25", now=NOW)["fsr_audit"], "NA")
    check("tomorrow         -> NA", describe("2026-08-26", now=NOW)["fsr_audit"], "NA")
    check("past + no roster -> NA", describe("2026-08-24", now=NOW)["fsr_audit"], "NA")
    check("cancelled        -> NA",
          describe("2026-09-01", active=False, now=NOW)["fsr_audit"], "NA")
    check("only three values ever", sorted(set(AUDIT.values())),
          ["NA", "graded", "needs grading"])
    check("every status maps", sorted(AUDIT), sorted(ORDER))
    # the whole point of deriving it: the two columns cannot disagree
    check("test_audit_tracks_status",
          all(audit_label(describe(d, registered=r, graded_count=g, active=a,
                                   now=NOW)["status"])
              == describe(d, registered=r, graded_count=g, active=a, now=NOW)["fsr_audit"]
              for d in ("2026-08-24", "2026-08-25", "2026-08-26", "2026-09-01")
              for r, g in ((0, 0), (3, 0), (3, 3))
              for a in (True, False)),
          True)

    print("\nan unreadable date is BAD DATE — never OPEN, never dropped")
    # This is the Aug 25 regression guard. "I can't read this date" used to
    # come back OPEN, so a finished class with a typo advertised itself as
    # upcoming and sat in the live bucket looking healthy.
    for bad in ("", "not a date", "09/01/2026", "TBD", None):
        d = describe(bad, now=NOW)
        check(f"test_bad_date_not_open {bad!r:14}",
              (d["status"], d["lifecycle"], d["fsr_audit"]),
              ("BAD DATE", ACTION, "NA"))
    # ...but an Excel datetime cell is a GOOD date, not a broken one
    check("test_excel_datetime_is_fine",
          describe("2026-09-01 00:00:00", now=NOW)["status"], "OPEN")
    check("...and normalises to the same day",
          describe("2026-09-01 00:00:00", now=NOW)["status"]
          == describe("2026-09-01", now=NOW)["status"], True)

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
