# M&A Supply — Training Events Landing Page

A local, no-build landing page for M&A Supply training-class signups.
**One page template per class**, selected by an `?event=<id>` code in the URL —
so each class gets its own link, and each link gets its own **QR code**.
Submissions are written one row per signup into a local SQLite DB, exportable to
`.xlsx` in the exact column order of John's sheet.

**Stack:** Python standard library + `openpyxl` (read xlsx) + `segno` (QR codes).
No Node, no Vercel, no build step.

## Run it

```sh
python3 server.py          # http://localhost:8000
python3 server.py 9000     # custom port
```

> Changed `server.py`? Stop the old one first (`Ctrl+C`, or
> `lsof -ti tcp:8000 | xargs kill`) before restarting. Static (HTML/CSS/JS) and
> `events.xlsx` edits are picked up live — just refresh.

### Serving a different catalog (e.g. the June test)

Point the server at any catalog with the `EVENTS_XLSX` env var (path relative to
the project, or absolute) — your real `data/events.xlsx` stays untouched:

```sh
python3 tools/make_june_test_xlsx.py                             # builds data/events_june_test.xlsx (10 classes)
EVENTS_XLSX=data/events_june_test.xlsx python3 server.py         # serve the June test set
EVENTS_XLSX=data/events_june_test.xlsx python3 tools/make_qr.py  # QR codes for those 10 classes
```

## How a class link works

```
QR / link:  http://localhost:8000/?event=nashville-fit-2026-04-29
                                          │
                       page reads ?event= │ GET /api/event?id=…
                                          ▼
data/events.xlsx ──> fills hero + card + branch dropdown ──> dealer fills form
                                                                   │ submit
                                          POST /api/register ──> data/registrations.db
                                                                   │
                                          GET /api/export.xlsx <───┘  (8-column .xlsx)
```

- No `?event=` → page shows a list of available classes.
- Unknown `?event=` → friendly "This class link is not active."

## Editing classes

Everything lives in **`data/events.xlsx`** (edit in Excel, refresh — no restart):

- `events` sheet — one row per class (one location = one QR), columns left→right:
  `active, event_id, region, branch, weekday, event_date, start_time, end_time,
  topic, event_location, host_label, capacity, notes`.
  - `active` = TRUE/FALSE (FALSE → hidden; link shows "not active").
  - `event_id` = slug in the URL (e.g. `nashville-fit-2026-04-29`).
  - `weekday` is auto-derived from the date if left blank; `capacity`/`notes` optional.
  - The combined `date_info` and time displays are **derived**, so they can't be mistyped.
  - **To add a class:** copy the last row, change the fields, keep `active = TRUE`,
    save, then `python3 tools/make_qr.py` for the new QR. No code changes.
- `branches` sheet — `branch` (dropdown list) + `territory_manager`. TM is **not**
  written to registrations by default (see `FILL_TM_FROM_BRANCH` in `config.py`).

Reset to seed data: `python3 tools/make_seed_xlsx.py`.

## QR codes

```sh
python3 tools/make_qr.py                              # encodes http://localhost:8000/?event=<id>
python3 tools/make_qr.py https://your-domain.com      # use your real host for production
```

Writes a PNG + SVG per class into `qr/`.

> A QR pointing at `http://localhost:8000` only works on **this machine**. To
> hand QRs to dealers, the app must be hosted at a public URL — then pass that
> URL to `tools/make_qr.py`.

## Stored columns (exact order — matches John's sheet)

```
date_info | Contact Email | Company Name | Account Number |
# Attending | Names of Attendees | Branch Location: | Territory Manager
```

- `date_info` is built server-side, e.g.
  `WEDNESDAY, APRIL 29, 2026_9AM- 3PM_ FIT INSTALL & COMMISSIONING _ @ NASHVILLE BRANCH`.
- `# Attending` and `Names of Attendees` come from the dynamic attendee list
  (count + names joined; a picked role appears as `Name (Role)`).
- **`Territory Manager` is stored blank** — it isn't determined by branch in the
  real data, so M&A fills it in afterward.

**Live Excel file:** SQLite (`data/registrations.db`) is the safe write target, but
after every submit the server rewrites **`data/registrations.xlsx`** from it
(atomic + lock-guarded). Just open that file — it's always current, no export step.
If it's open in Excel during a submit, the row still saves and the file catches up
on the next one. `/api/export.xlsx` still works too.

## Print QR codes for John

`http://localhost:8000/qr-pack` renders one card per active class — full details,
the register link, and a QR code — styled for printing. John clicks **Print /
Save as PDF**. (QRs encode whatever host the page was opened on, so once the app
is hosted at a real domain, the printed codes point there automatically.)

## Endpoints

| Method | Path                  | Purpose                                  |
|--------|-----------------------|------------------------------------------|
| GET    | `/`, `/class.html`    | Landing page (reads `?event=`)           |
| GET    | `/qr-pack`            | Printable sheet: every class + QR + link (Print → Save as PDF) |
| GET    | `/api/event?id=<slug>`| One event's details + branch list        |
| GET    | `/api/events`         | All visible events (index list + QR)     |
| POST   | `/api/register`       | Validate + store one registration        |
| GET    | `/api/registrations`  | All registrations as JSON (admin view)   |
| GET    | `/api/export.xlsx`    | Download registrations as `.xlsx`         |

## Files

```
server.py              thin entry point: builds the repo, wires routes, serves
config.py              single source of truth (paths, export columns, roles, flags)
src/
  catalog.py           reads data/events.xlsx; date/time formatting; event views
  registrations.py     validates a submit -> structured registration
  export.py            registrations -> .xlsx (exact column order) + live mirror
  qr_pack.py           printable /qr-pack sheet
  routes.py            HTTP handler (routing only)
  db/
    schema.sql         normalized DDL (companies, people, events, registrations, attendees)
    repository.py      backend-agnostic interface
    sqlite_repo.py     SQLite implementation (only module that imports sqlite3)
static/                index.html, styles.css, app.js
data/events.xlsx       the classes + branch list you edit
data/registrations.db  created on first run (normalized signups land here)
tools/
  make_seed_xlsx.py    regenerates data/events.xlsx (events + branches)
  make_june_test_xlsx.py  builds the 10-class June test catalog
  make_qr.py           generates qr/<event_id>.png + .svg per class
  data_cleaning/       one-off cleaner for real dealer data (PII, gitignored)
qr/                    generated QR codes
```

## Data model (normalized, SQLite — migration-ready)

Registrations are no longer one flat row. The repository (`src/db/`) splits each
submit across:

- `companies` (by name + account #) and `people` (attendees, by name + company) —
  upserted on every submit, so **returning** vs **new** is detected automatically
  (`registration_attendees.is_returning`, surfaced in `/api/registrations`).
- `events` — a cache synced from `events.xlsx` (which stays the editable catalog).
- `registrations` + `registration_attendees` — one parent row per submit, one child
  row per attendee.

All SQL lives in `sqlite_repo.py` behind the `Repository` interface, so migrating
to Postgres later means adding one sibling module and flipping `DB_BACKEND` in
`config.py` — no caller changes. The 8-column `.xlsx` export is rebuilt from these
tables, unchanged.
