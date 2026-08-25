# M&A Training Hub — AUG 3 snapshot

A frozen, working copy of the app as of **3 Aug 2026**. The original project one
level up is untouched — fall back to it any time.

```
_MandA_AUG_3/
  README_WRAPUP.md   ← this file
  app/               ← the running app (own .venv, own data)
```

## Run it

```bash
cd "/Users/yerik/_apple_lib/_peg_ProgEnvGit/a0ds_CLIENTS/JhonWard/_landing_page/_MandA_AUG_3/app"
./.venv/bin/python server.py      # venv already built
# then open http://127.0.0.1:8000
```

Rebuilding the venv from scratch, if ever needed:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt   # openpyxl, segno, reportlab, PyYAML
```

> `pip install openpyxl segno pyyaml` is **not** enough — `reportlab` is required
> for the reminder-letter PDFs. Always use `requirements.txt`.

## The URLs that exist

| URL | What it is |
|---|---|
| `/` | Class list. Public by default. |
| `/?event=<id>` | One class — the whole product. |
| `/qr-pack` | Printable QR sheet (flier page 1, QR page 2) |
| `/reminder-letter?...` | One student's PDF letter (admin-gated) |
| `/refresher`, `/data-cycle` | Info pages |

**`/manage`, `/admin` and `/dealers` no longer exist** — they were consolidated
into the class page and deliberately deleted. They return 404 by design.

## One page, three lenses

Open a class and pick a view. Codes are checked **server-side**; a locked mode is
never sent the roster at all.

| Lens | Sees | Code |
|---|---|---|
| **User** (blue) | Register your team | none — default |
| **Admin** (orange) | Edit class, address, roster, flier, **Add a class**, reminder letters | `CORP7000` |
| **FSR** (green) | Roster, grading, close-out | `MAA` |

**ADMIN-VIEW** in the top nav (class list only) adds registered counts, status
and reminder history to the master table, and reveals **ADD A CLASS**.

Admin and FSR have **separate** codes and they do not cross: `CORP7000` never opens
FSR, `MAA` never opens Admin. Codes live in `data/hub_codes.json` — change them
there, no code edit needed.

## Where data lives

| What | Where | Notes |
|---|---|---|
| Classes | `data/OFFICIAL_CLASS_SCHEDULE.xlsx` | the catalog; read fresh on every request |
| Registrations + grades + audit | `data/registrations.db` | SQLite, source of truth |
| Excel mirror | `data/registrations.xlsx` | rewritten after every signup |
| Class address overrides | `data/class_address.json` | floating overlay, never touches the catalog |
| Fliers | `data/fliers/` | one per class |
| Reminder ledger | `data/email_campaign/outbox.xlsx` | drives the "reminders sent" columns |
| Master workbook from John | `_data_in/` | `..._latest.xlsx` is the newest |

## Check it before trusting it

```bash
./.venv/bin/python tools/data_audit.py --server
```

30+ assertions: catalog integrity, timezone coverage, overbooking, orphan rows,
mirror drift, and the security gates (locked modes leak nothing). Exit 0 = clean.
**Run it after anyone edits the workbook.**

## Documents

| File | What it is |
|---|---|
| `WALKTHROUGH.html` | Full visual walkthrough — every screen and role, start to finish |
| `BLUEPRINT.html` | System map: routes, lenses, data dictionary, invariants |
| `app/docs/hub_data_blueprint.html` | Per-operation data flows — what reads/writes what |

## Known gaps (carried into this snapshot)

- `.ics` calendar invites use floating time — wrong hour across zones.
- Registrations are hard-deleted; the audit log snapshots them first, so a
  removal is reconstructable but not one-click undoable.
- A dealer can register twice for the same class — no dedup.
- `date_info` is frozen at signup; changing a class date later doesn't re-sync it.

## John's 3 Aug master — LOADED

Built from `_data_in/MASTER COPY  Training Hub Info Phase 1 _ AUG 3.xlsx`:

- **84 classes** (81 live to dealers, 3 internal) across **20 branches**, Aug–Dec 2026
- **224 program dealers**, **169 personnel**
- All mock registrations, fliers and reminder history cleared — the hub is at zero

`tools/build_from_master.py` now **auto-selects the newest** `MASTER COPY*.xlsx`
in `_data_in/`, accepts either `Top Tier Dealers` or the old `Tier 1 Dealers`
sheet name, and **derives any missing timezone** from the branch — refusing to
build if one can't be determined.

To refresh after John sends a new workbook:

```bash
cd _MandA_AUG_3/app
cp ~/Downloads/"MASTER COPY ... .xlsx" _data_in/
./.venv/bin/python tools/build_from_master.py
./.venv/bin/python tools/data_audit.py --server
```
