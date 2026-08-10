# ADR: Single Class Catalog & Edit Path

**Status:** Accepted
**Date:** 2026-07-13

## Decision

We will have **one canonical class catalog** and **one write path** for editing it:

- The **only source of truth** for classes (date, time, topic, branch, capacity, trainer,
  status, etc.) is `data/OFFICIAL_CLASS_SCHEDULE.xlsx`, sheet `events` (see `config.EVENTS_XLSX`).
- The **only code that writes** to this catalog is `src/manage.py` (the `/manage` hub).
- The SQLite table `events` in `data/registrations.db` is a **cache** of the Excel catalog
  (populated via `catalog.event_cache_row()`), used only for referential integrity and
  reporting. It must never be edited directly.

All other modules (registration, Admin Hub, Dealer Hub, exports, chat) treat this catalog
as **read-only**.

## How classes work today (3 layers)

**A. Class catalog — source of truth** · `data/OFFICIAL_CLASS_SCHEDULE.xlsx` (sheets `events`, `branches`)
- Read side: `src/catalog.py` — `load_catalog()` returns `events_by_id`, `branch_list`,
  `branch_to_tm`; `public_events()`, `event_view()`, `build_date_info()`, `missing_info()`
  turn rows into UI-friendly data.
- Write side: `src/manage.py` — `list_classes()`, `update_class()`, `adjust_seats()`
  (never below seats already booked), `set_active()` (cancel / reinstate),
  `create_class()` (append a new row with a unique `event_id`).

**B. Normalized DB (registrations + events cache)** · `data/registrations.db`
- `events` — one cache row per class (from Excel via `event_cache_row()`).
- `registrations` — one per signup (company + contact).
- `registration_attendees` — one per person/seat, incl. attendance + grading fields.
- `companies`, `people` — deduplicated dealer + person info.

**C. Flat export layer (the "one table" everyone sees)** · `src/export.py` + repo
- `repo.all_registrations_flat()` (in `src/db/sqlite_repo.py`) joins class info +
  company/person info + attendance/grades into one dict per row.
- `write_registrations_xlsx(repo)` rewrites `data/registrations.xlsx` atomically after
  every submit. That flat row is the ONE canonical view of "registrations + classes."

## Rationale

Previously, classes were spread across `events.xlsx`, various demo builders, and ad-hoc DB
edits. This caused:
- Orphan registrations when event IDs changed,
- Mismatched dates/capacities between Excel and the site,
- Confusion about which file or table to trust.

By standardizing on a single Excel catalog and a single write path, we ensure:
- John can always see and edit the full schedule in one familiar place (Excel),
- The app can safely cache and join against a stable `event_id`,
- All portals and exports (landing, Admin Hub, Dealer Hub, `data/registrations.xlsx`) see
  the same view.

## Rules

1. **Do not edit the `events` DB table directly.**
   To change a class, update `OFFICIAL_CLASS_SCHEDULE.xlsx` via `src/manage.py`
   (or, in an emergency, by careful Excel edit followed by a sync).

2. **Do not change `event_id` once a class has registrations.**
   To cancel or reschedule, use:
   - `set_active(repo, event_id, False)` to cancel, or
   - create a **new** class with a new `event_id` and move attendees if needed.

3. **All views must depend on the same data:**
   - Landing + `/api/event` validate against `catalog.load_catalog()` (active events only).
   - Admin Hub, TM/Teacher portals, and Dealer Hub must use `repo.all_registrations_flat()`
     (or its DB equivalent) joined to `events`.
   - `data/registrations.xlsx` must be regenerated via `write_registrations_xlsx(repo)` —
     never manually edited.

4. **New catalogs must always go through `EVENTS_XLSX`.**
   If John provides a new schedule (PDF / Excel), we:
   - Generate `OFFICIAL_CLASS_SCHEDULE.xlsx` (`tools/make_official_schedule.py` or equivalent),
   - Point `EVENTS_XLSX` at it,
   - Run a sync if needed, and
   - Verify 3 sample classes across landing, Admin, Dealer Hub, and export.

## Risks to watch (tied to the files above)

- **`EVENTS_XLSX` mismatch** — if `config.EVENTS_XLSX` points somewhere other than
  `OFFICIAL_CLASS_SCHEDULE.xlsx`, catalog & manage modify the wrong file. Keep them equal.
- **Manual Excel edits that bypass `manage.py`** — hand-editing `event_id` or deleting rows
  breaks `manage._find_row` and orphans registrations. Use `set_active()` / `update_class()`.
- **Event cache falling out of sync** — always use `event_cache_row(ev)` when saving
  registrations; a bulk sync script must refresh all `events` rows from Excel.
- **Multiple "catalog" files** — old `data/events.xlsx` / test xlsx must stay archived and
  unreferenced. Everything reads through `EVENTS_XLSX` only.

## Consequences

- There is exactly **one place** to look when class details look wrong:
  `OFFICIAL_CLASS_SCHEDULE.xlsx`.
- Any code that writes classes outside `src/manage.py` is a bug and must be removed or
  refactored.
- Old catalogs (`data/events.xlsx`, the summer/fall demo generators) are archived in
  `_archive_data/superseded_catalogs/` and not used by the live system.

## UI note — "needs info" triangle

Classes missing time / trainer / location are flagged with a ⚠️ triangle **only inside the
Edits & Updates hub (`/manage`)** — a team-facing cue to complete them before publishing.
The public landing page never shows the triangle. The flag is derived live by
`catalog.missing_info(ev)`, so it stays accurate after any edit.
