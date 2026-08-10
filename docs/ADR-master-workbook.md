# ADR: MASTER Workbook as Single Data Source

**Status:** Accepted · **Date:** 2026-07-13
Builds on [`ADR-classes-catalog.md`](ADR-classes-catalog.md) and
[`RULE-classes-and-registrations.md`](RULE-classes-and-registrations.md).

## Decision

The only file humans edit for Phase 1 is:

- **`_data_in/MASTER COPY  Training Hub Info Phase 1.xlsx`** with three sheets:
  - `Tech Team Calendar` — the class schedule,
  - `Tier 1 Dealers` — the dealer list,
  - `M&A Personnel` — internal staff / TMs / trainers.

Every class/dealer/personnel file the app reads is **generated** from this workbook by
`tools/build_from_master.py` (+ `tools/make_codes.py`). The app's runtime file shapes are
unchanged — only the *source* of those files moved upstream to the MASTER.

## The build pipeline

```
MASTER COPY  Training Hub Info Phase 1.xlsx  (3 tabs, human-edited)
        │
        ├─ tools/build_from_master.py
        │      Tech Team Calendar → data/OFFICIAL_CLASS_SCHEDULE.xlsx (events + branches)
        │                         → chat_bot/data_global/classes_sim.csv
        │      Tier 1 Dealers     → data/dealers.xlsx  (John's "Results" shape: banner rows +
        │                           header "Customer ID | Customer Name | Sales Rep Name (Cust)")
        │      M&A Personnel       → data/employees.xlsx (Legal_Firstname, Legal_Lastname, Position, Work_Location)
        │
        ├─ tools/make_codes.py            → chat_bot/chat_config/tm_keys.yaml + trainer_codes.yaml
        │                                   + data/access_codes.xlsx + dealers_sim.csv (all REAL)
        ├─ tools/sync_chat_from_db.py     → resets chat history to REAL (zero until real signups;
        │                                   overwrites the placeholder history make_codes emits)
        └─ cd chat_bot && …-m chat_rag.build_index   → rebuild chat indexes
```

Then restart the server. `config.EVENTS_XLSX` already points at
`data/OFFICIAL_CLASS_SCHEDULE.xlsx`, so `src/catalog.py` / `src/manage.py` pick up the new
catalog with no code change.

## Runtime shapes are left ALONE (why nothing breaks)

- **Classes** — `data/OFFICIAL_CLASS_SCHEDULE.xlsx`, sheets `events` + `branches`, exact
  headers `src/catalog.py` and `src/manage.py` expect.
- **Dealers** — `data/dealers.xlsx` in John's export shape; `src/dealers.py` detects the
  `Customer ID` header row and flips `Last, First` reps unchanged.
- **Personnel / keys** — `data/employees.xlsx` in the column order `tools/make_codes.py`
  reads; it produces `tm_keys.yaml` / `trainer_codes.yaml` / `access_codes.xlsx` exactly as before.
- **Registrations** — untouched: `registrations.db` → `all_registrations_flat()` →
  `data/registrations.xlsx` (see the registrations rule doc).

## Messy-data handling (real MASTER quirks the builder normalizes)

- Date typos (e.g. `10/2002026` → `2026-10-20`) via a fix map; unparseable dates are
  skipped and logged, never silently dropped.
- Location formats `City, ST` / `City ST` / `City, St.` → parsed to city + 2-letter state.
- Business-hour times `9:00 - 1:00 cst` → `09:00`/`13:00` + timezone `CST`.
- Multi-trainer cells (`Terry / Shane`, `Joey T, Brian T`) kept verbatim; `ALT TRAINER`
  (e.g. `DAIKIN REP`) goes to notes.
- The internal **Daikin Tech Services Conference** (San Antonio, no time) is kept but
  `active = False` — captured, never shown to dealers.

## Rules

1. **Do not edit** `OFFICIAL_CLASS_SCHEDULE.xlsx`, `dealers.xlsx`, `employees.xlsx`,
   `tm_keys.yaml`, `trainer_codes.yaml`, or `classes_sim.csv` by hand — they are build outputs.
   (Small live class tweaks may still go through `/manage`, which writes the catalog; a full
   rebuild from MASTER will overwrite them.)
2. **Any change to classes, dealers, or personnel** goes into the MASTER workbook, then
   `tools/build_from_master.py` (+ the follow-up steps above).
3. **No new feature reads the MASTER directly** — it reads the existing runtime files/shapes.
4. **Old inputs are archive-only:** `_data_in/M&A Training Schedule for Hub.pdf` and the
   hand-built generators (`make_events_2026.py`, `make_events_fall2026.py`,
   `make_official_schedule.py`) live in `_archive_data/` and no longer drive the system.

## Consequences

- Exactly one place for John and Yeriko to edit core data: the MASTER workbook.
- All runtime files regenerate consistently — no drift, no orphan references.
- The Phase-1 MASTER corrected real gaps the hand-built catalog had missed: an **August 18**
  Daikin onboarding class, the Daikin ductless/FIT classes, the full Santa Fe dehumidifier
  tour, and proper topic names (e.g. `RUUD COMMERCIAL PRODUCT`). Business "example" classes
  that were never in the official calendar are correctly absent.
