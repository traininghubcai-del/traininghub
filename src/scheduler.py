"""The daily reminder run, inside the web process.

The 7/3/1-day schedule only means something if something runs it every day.
Until now nothing did in production: run_sender() was reachable from the local
demo console and from the Admin "send reminders" button, so a class's reminders
went out when a person remembered to press a button. This is the part that
remembers.

A thread rather than a cron service because the app is a single process on a
single host, and because the dedupe that makes this safe already lives in the
outbox ledger, not in the scheduler. That matters more than it sounds: a deploy,
a crash or a restart mid-run loses this thread's memory of what it did, and the
ledger still stops any dealer getting a second copy. Which is also why a missed
day self-heals — due_jobs() picks up anything overdue and never sent.
"""
import threading
import time
from datetime import date, datetime

from config import EMAIL_SEND_HOUR

# How often the thread wakes to check the clock. Fine-grained enough that the
# run starts within a few minutes of the hour, coarse enough to be free.
_TICK_SECONDS = 300

_last_run = None            # the date of the last completed run, this process


def _due(now):
    """True when today's run hasn't happened yet and the hour has arrived."""
    return _last_run != now.date() and now.hour >= EMAIL_SEND_HOUR


def run_once(today=None):
    """Generate today's emails and send everything due. Returns the sent jobs.

    Kept separate from the loop so it can be called by hand — from a shell, or
    from a real cron service later — without starting a thread.
    """
    from src.email_campaign import generate_emails, run_sender
    today = today or date.today()
    generate_emails(today)          # refresh the rendered HTML + the schedule sheet
    return run_sender(today)


def _loop():
    global _last_run
    # Don't fire on boot. A restart at 4pm would otherwise run a job whose hour
    # passed hours ago — harmless thanks to the ledger, but it makes every
    # deploy look like a send, and buries the real one in the audit trail.
    _last_run = date.today()
    while True:
        time.sleep(_TICK_SECONDS)
        now = datetime.now()
        if not _due(now):
            continue
        try:
            sent = run_once(now.date())
            print(f"[scheduler] {now:%Y-%m-%d %H:%M} daily reminder run: "
                  f"{len(sent)} email(s)")
        except Exception as e:  # noqa: BLE001 - a bad day must not kill the thread
            print(f"[scheduler] {now:%Y-%m-%d %H:%M} run failed: {type(e).__name__}: {e}")
        # Marked done either way. A failure that repeats every five minutes for
        # the rest of the day is worse than one that waits for tomorrow, and
        # failed rows are retried by the ledger on the next run regardless.
        _last_run = now.date()


def start():
    """Start the daily run in the background. Daemon, so Ctrl+C still exits."""
    threading.Thread(target=_loop, daemon=True, name="reminder-scheduler").start()
