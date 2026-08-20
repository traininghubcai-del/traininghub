# RULE — Mail goes out through Brevo, and only when told to

**Status:** Accepted · 2026-08-20
**Code:** `config.py` (settings) · `src/email_campaign.py` (send) · `src/scheduler.py` (daily run)
**Test it:** `.venv/bin/python tools/mail_test.py`

## The rule

All mail — registration receipts and 7/3/1-day class reminders — leaves through
the **Brevo SMTP relay**, configured entirely from environment variables in
Railway. No credential is ever committed, and no default in the code points at a
different provider.

## Transport: the HTTP API, not SMTP

**Railway blocks outbound SMTP on every port.** A perfectly correct SMTP setup
times out there — port 587 and 465 both, with no error a person could act on.
So the deployed app sends over **Brevo's HTTP API** (plain HTTPS on 443), which
nothing blocks.

Set `BREVO_API_KEY` to an API key from Brevo → SMTP & API → **API keys** tab
(starts `xkeysib-`), and the SMTP variables are ignored entirely. Without it the
app falls back to SMTP, which is what runs locally and on a host that permits it.

`/api/mail-status` reports `"transport": "api"` or `"smtp"` so there is never a
question about which path is carrying mail.

⚠️ The **API key** (`xkeysib-`) and the **SMTP key** (`xsmtpsib-`) are different
credentials on the same Brevo page and are not interchangeable in either
direction — tested.

## The five variables

Set in Railway → the service → Variables. All five, or nothing sends.

| Variable | Value | Where it comes from |
|---|---|---|
| `SMTP_HOST` | `smtp-relay.brevo.com` | already the default; set it anyway so it's visible |
| `SMTP_PORT` | `587` | default |
| `SMTP_USER` | Brevo's **SMTP login**, e.g. `9a1b2c001@smtp-brevo.com` | Brevo → SMTP & API → SMTP tab, the "Login" field |
| `SMTP_PASSWORD` | the **SMTP key**, `xsmtpsib-...` | same page, "SMTP key" |
| `EMAIL_SEND_ENABLED` | `1` | nothing sends until this is on |

Plus `EMAIL_FROM` (defaults to `traininghubcai@gmail.com`), which **must be a
sender Brevo has verified** — Brevo → Senders.

## The two mistakes that cost an afternoon

**1. `SMTP_USER` is not the from address.** Gmail uses one address for both, so
it's a natural assumption and it's wrong here: Brevo issues its own login, which
looks like `9a1b2c001@smtp-brevo.com`. Putting `traininghubcai@gmail.com` there
fails with `535 5.7.8 Authentication failed` — which reads like a bad key, and
isn't one.

**2. The SMTP key is not the API key.** Brevo's SMTP & API page issues both. SMTP
wants `xsmtpsib-...`; `xkeysib-...` is for the HTTP API and will not log in.

`tools/mail_test.py` names both of these if it sees them.

## Two switches, not one

- `EMAIL_SEND_ENABLED` — mail may leave the machine. Off ⇒ every send is written
  to the outbox as `SIMULATED` and nothing is delivered.
- `EMAIL_DAILY_SEND` — the app may decide *on its own* when to send, via the
  daily run in `src/scheduler.py`.

Deploy with the first on and the second off. That gives working registration
receipts and a working Admin "send reminders" button, with the 7/3/1-day
schedule still dormant — and no chance of a first deploy mailing a backlog.
Turn the second on once the first has been seen to work.

With `EMAIL_DAILY_SEND=1`, also set `EMAIL_SEND_HOUR` (default `8`) and
`TZ=America/Chicago` — containers run UTC, so without `TZ` hour 8 is 3am local.

## The outbox is the ledger, and its status strings are load-bearing

Every send appends a row to `data/email_campaign/outbox.xlsx` with a status.
`sent_keys()` treats a row as already-sent **unless its status starts with
`FAILED`** — so a failure retries on the next run, and anything else never sends
twice. That is what makes the daily run, the Admin button and the receipt path
safe to all fire at once, and what makes a missed day self-heal.

Two consequences worth stating:

- **A `SIMULATED` row counts as sent.** Running the sender with
  `EMAIL_SEND_ENABLED` off burns those reminders — the dealer will never get the
  real one. Never point a simulated run at the live `data/` directory; use
  `APP_DATA_DIR=/tmp/scratch` on a copy.
- **Failure text is written in full.** The provider's own rejection is invisible
  from the UI, so the outbox is the only place it survives.

## Checking it without mailing a dealer

```
.venv/bin/python tools/mail_test.py                    # settings + a real login
.venv/bin/python tools/mail_test.py --to you@work.com  # also send one test email
railway run .venv/bin/python tools/mail_test.py        # against the deployed env
```

Or, on the live site, `GET /api/mail-status?code=<admin>&probe=1` — same login
check, plus the last few outbox rows with their real failure text. It reports the
login in full (a username, not a secret) precisely because that's the field that
is usually wrong; the key is only ever a boolean.
