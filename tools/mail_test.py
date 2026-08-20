"""Prove the mail settings work, without mailing a dealer.

Sending is the one part of this app that can't be verified by reading the code:
it depends on three values held by Brevo and Railway, and every way of getting
them wrong produces the same silence. This asks the relay directly.

    .venv/bin/python tools/mail_test.py                    # check settings + log in
    .venv/bin/python tools/mail_test.py --to you@work.com  # also send one real email

Reads the environment, exactly like the server does, so running it under the
same env as the app (`railway run .venv/bin/python tools/mail_test.py`) tests
what the app will actually do — not what a local .env says it should.

Exit code 0 = the relay accepted us, 1 = it did not.
"""
import argparse
import smtplib
import sys
from email.message import EmailMessage
from email.utils import formataddr
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import (BREVO_API_KEY, EMAIL_FROM, EMAIL_FROM_NAME,  # noqa: E402
                    EMAIL_REPLY_TO, EMAIL_SEND_ENABLED, SMTP_HOST,
                    SMTP_PASSWORD, SMTP_PORT, SMTP_SSL, SMTP_USER)
from src.email_campaign import (api_probe, api_send, missing_settings,  # noqa: E402
                                smtp_connect, transport)


def _mask(secret):
    """Enough of the key to tell which one is loaded, never enough to use it."""
    if not secret:
        return "(not set)"
    return f"{secret[:12]}...{secret[-4:]}  ({len(secret)} chars)"


def _fake_job(to):
    """A real class from the catalog, with a fake registration attached.

    Built through confirmation_job() rather than hand-rolled, so the test renders
    and attaches through exactly the code a dealer's receipt goes through — a
    hand-made stand-in would pass while the real template was broken. The
    registration is fake and the class is only read, so this can never mail a
    dealer or touch the database.
    """
    from datetime import date

    from src.catalog import is_active, load_catalog
    from src.email_campaign import confirmation_job

    events, _, _ = load_catalog()
    upcoming = sorted((e for e in events.values()
                       if is_active(e) and str(e.get("event_date", "")) >= str(date.today())),
                      key=lambda e: str(e.get("event_date", "")))
    if not upcoming:
        raise SystemExit("No upcoming class in the catalog to build a test email from.")

    reg = {"event_id": upcoming[0]["event_id"], "contact_email": to,
           "company_name": "Mail test — not a real registration", "num_attending": 1}
    job = confirmation_job(0, reg, [{"name": "Mail test", "role": ""}])
    if job is None:
        raise SystemExit("Could not build a test email from the catalog.")
    job["subject"] = "Training Hub — mail test"
    return job


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", help="send a real test email to this address")
    args = ap.parse_args()

    print("--- settings the app is running with ---")
    print(f"  TRANSPORT           {transport().upper()}"
          f"{'   (Brevo HTTP API, port 443)' if transport() == 'api' else '   (SMTP relay)'}")
    print(f"  BREVO_API_KEY       {_mask(BREVO_API_KEY)}")
    print(f"  SMTP_HOST           {SMTP_HOST}")
    print(f"  SMTP_PORT           {SMTP_PORT}   ({'implicit TLS' if SMTP_SSL else 'STARTTLS'})")
    print(f"  SMTP_USER           {SMTP_USER or '(not set)'}")
    print(f"  SMTP_PASSWORD       {_mask(SMTP_PASSWORD)}")
    print(f"  EMAIL_FROM          {EMAIL_FROM}")
    print(f"  EMAIL_REPLY_TO      {EMAIL_REPLY_TO}")
    print(f"  EMAIL_SEND_ENABLED  {EMAIL_SEND_ENABLED}")

    # Named separately from the login attempt: "you never set SMTP_USER" and
    # "Brevo rejected your SMTP_USER" are different problems with different fixes.
    missing = missing_settings()
    if missing:
        print("\nFAIL — not configured:")
        for m in missing:
            print(f"  - {m}")
        return 1

    # The API path shares nothing with SMTP but the sender, so it gets its own
    # short circuit rather than being threaded through the checks below.
    if transport() == "api":
        print("\n--- checking the Brevo API key ---")
        result = api_probe()
        print(result)
        if result.startswith("FAILED"):
            return 1
        if not args.to:
            print("\nNo --to given, so nothing was sent. The key works.")
            return 0
        print(f"\n--- sending a test email to {args.to} ---")
        job = _fake_job(args.to)
        try:
            api_send(job, args.to)
        except Exception as e:  # noqa: BLE001
            body = getattr(e, "read", lambda: b"")().decode("utf-8", "replace")[:300]
            print(f"FAIL — {type(e).__name__}: {e} {body}")
            print("  A 400 here is usually EMAIL_FROM not being a verified sender:")
            print("  add and confirm it under Brevo -> Senders.")
            return 1
        print(f"OK — accepted for delivery to {args.to}. Check the inbox (and spam).")
        if not EMAIL_SEND_ENABLED:
            print("\n  ! EMAIL_SEND_ENABLED is off, so the app itself is still only")
            print("    simulating sends. Set it to 1 to let real mail go out.")
        return 0

    if SMTP_USER == EMAIL_FROM and SMTP_HOST.endswith(("brevo.com", "sendinblue.com")):
        print("\n  ! SMTP_USER is the same as EMAIL_FROM. Brevo issues its own SMTP")
        print("    login (SMTP & API -> SMTP), which is not the sending address.")
    if SMTP_PASSWORD.startswith("xkeysib-"):
        print("\n  ! SMTP_PASSWORD looks like a Brevo API key. SMTP wants the SMTP")
        print("    key from the same page — it starts with xsmtpsib-.")

    print(f"\n--- connecting to {SMTP_HOST}:{SMTP_PORT} ---")
    try:
        conn = smtp_connect()
    except smtplib.SMTPAuthenticationError as e:
        print(f"FAIL — login rejected: {e.smtp_code} "
              f"{e.smtp_error.decode('utf-8', 'replace').strip()}")
        print("  The host and port are fine — the credentials are not. Copy both")
        print("  the login and the key from Brevo -> SMTP & API -> SMTP.")
        return 1
    except Exception as e:  # noqa: BLE001 - this is the tool that reports errors
        print(f"FAIL — {type(e).__name__}: {e}")
        return 1
    print(f"OK — logged in as {SMTP_USER}")

    if not args.to:
        conn.quit()
        print("\nNo --to given, so nothing was sent. The credentials work.")
        return 0

    # A real send is the only thing that exercises sender verification: Brevo
    # accepts the login first and rejects an unverified From afterwards.
    msg = EmailMessage()
    msg["Subject"] = "Training Hub — mail test"
    msg["From"] = formataddr((EMAIL_FROM_NAME, EMAIL_FROM))
    msg["To"] = args.to
    msg["Reply-To"] = EMAIL_REPLY_TO
    msg.set_content("This is a test from the Training Hub. If you got it, "
                    "registration receipts and class reminders will send too.")
    print(f"\n--- sending a test email to {args.to} ---")
    try:
        conn.send_message(msg)
    except smtplib.SMTPSenderRefused as e:
        print(f"FAIL — {EMAIL_FROM} refused as the sender: {e.smtp_code} {e.smtp_error!r}")
        print("  Add and confirm it under Brevo -> Senders, or set EMAIL_FROM to")
        print("  an address that is already verified there.")
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"FAIL — {type(e).__name__}: {e}")
        return 1
    finally:
        try:
            conn.quit()
        except Exception:  # noqa: BLE001
            pass
    print(f"OK — accepted for delivery to {args.to}. Check the inbox (and spam).")
    if not EMAIL_SEND_ENABLED:
        print("\n  ! EMAIL_SEND_ENABLED is off, so the app itself is still only")
        print("    simulating sends. Set it to 1 to let real mail go out.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
