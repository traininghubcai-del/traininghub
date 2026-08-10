# M&A Supply — Training Hub · Blueprint & Checkpoints

> Living document. Two audiences in one file:
> **Part 1–4** = what to *say/show* (executive + demo + roadmap).
> **Part 5–9** = what to *build* (technical blueprint, file map, how-to, checkpoints).
>
> Last verified: **2026-06-11** (Huntsville demo week). Everything marked ✅ was run and confirmed.

---

## 1. Executive summary (the up-front pitch)

> "We've built a working training-registration system that's already aligned with your
> existing Excel sheets and ready for QR-based signups. On top of that, we've built a
> **Training Assistant** chat with three modes — Public, Territory Manager, and Trainer —
> powered by a **local Llama model**, so dealer data never leaves the machine."

Two pillars, both demo-able today:
1. **Registration flow** — Excel-driven classes → per-class link + QR → dealer self-registration → clean Excel roster in John's exact format.
2. **Training Assistant** — a real local-LLM chat that answers about classes (Public), a TM's dealers (TM mode), and a trainer's rosters (Trainer mode).

---

## 2. What exists today (concrete, demo-able)

### 2.1 Class registration flow ✅
- **Single source of truth:** `data/events.xlsx` (sheets `events` + `branches`) defines every class — date, time, topic, branch, "Hosted by…" text, capacity. The server reads it live; nothing is hand-duplicated. Override with `EVENTS_XLSX=…` for test catalogs.
- **Per-class landing page:** stable URL `/?event=<id>` (e.g. `/?event=nashville-fit-2026-06-03`). Shows region/branch, topic, date/time, host label, and a "register your team" form (attendee list with roles, auto-counts).
- **Writes John's format:** on submit, derives the `date_info` string exactly like his sheets (`WEDNESDAY, APRIL 29, 2026_9AM- 3PM_ FIT INSTALL & COMMISSIONING _ @ NASHVILLE BRANCH`) and writes one row per registration. Columns: `date_info, Contact Email, Company Name, Account Number, # Attending, Names of Attendees, Branch Location:, Territory Manager`. Stored in SQLite (`data/registrations.db`), mirrored to `data/registrations.xlsx` after each submit, and downloadable at `/api/export.xlsx`.

### 2.2 QR-code workflow ✅
- `/` with no `?event=` → index of all active classes, each card with topic/region, date/time, registration link, and a generated **QR code** pointing at the right `?event=` URL.
- `/qr-pack` → printable QR sheet (Print → Save as PDF) for flyers/emails. Pre-generated PNG/SVG live in `qr/`.
- Scanning a QR lands a dealer directly on the correct class page.

### 2.3 Training Assistant chat ✅ (now functional, not just a shell)
- Floating launcher **"Ask the Training Hub"** (bottom-right) → panel with header, mode badge, **minimize/close**, and a **minimized bar** that preserves the session.
- **Three-mode toggle:** `Public · Territory Manager · Trainer`. Switching modes **resets the conversation** (new session, cleared log, dropped connection) so threads don't pile up.
- Per-mode hints, placeholders, suggestion chips, and a **Connect** field for TM key / Trainer code.
- **Powered by local Llama** (Ollama, `llama3.2:3b`). If Ollama is off, it **falls back to rule-based answers** — chat never breaks.

### 2.4 Email campaign (reminders 7/3/1 days before class) ✅
- **Pipeline:** `src/email_campaign.py` + demo console `email_demo.py` (menu: 1 generate, 2 send, 3 status, 4 preview, 5 seed). All output under `data/email_campaign/` (git-ignored, regenerable).
- **Generate:** one branded HTML email per registration per stage (`emails/0001_7day.html`, `_3day`, `_1day`) + `0001_invite.ics`. Same design language as the site (navy/blue palette, table-based inline CSS for email clients). 7-day = "lock your calendar" (Google Calendar button + .ics), 3-day = details + team list, 1-day = "Be prepared" checklist (pulls event `notes`, e.g. "Bring your gauges").
- **Schedule from Excel:** send dates derive live from `events.xlsx` class dates — change a date in Excel, every reminder reschedules. Full plan in `campaign_schedule.xlsx` (one row per email).
- **Sender is simulated:** `run_sender(today)` finds due emails (send_on ≤ today, class still upcoming, not already sent) and appends rows to `outbox.xlsx` — that sheet *is* the demo "send." Dedupe ledger = outbox (reg_id, stage) pairs, so it's safe to run daily; after deploy only `_deliver()` changes (SMTP/SES), the schedule/dedupe logic is already cron-shaped.
- **Per-student today = per-registration contact:** attendees have no emails yet (`people.email` is reserved); the contact gets the email listing their team.

---

## 3. Training Assistant — modes & behavior

| Mode | Auth | Answers about | Codes |
|---|---|---|---|
| **Public** | none | class catalog: topics, dates, locations, open seats | — |
| **Territory Manager** | TM access key | that TM's REAL program dealers; leadership keys see all territories | real keys in `data/access_codes.xlsx` (not in repo) |
| **Trainer** | trainer code | that trainer's classes: rosters, attendance, no-shows, upcoming | real codes in `data/access_codes.xlsx` (not in repo) |

**How Llama fits (local, private):** all AI logic is isolated in `chat_bot/AI_oLLama/`. It calls a local Ollama model. The model only ever sees: a strict system prompt (rules) + a small filtered CONTEXT block (relevant classes or the TM/Trainer snapshot) + the user's question. No dealer data leaves the machine. To go cloud later, swap the body of one function (`ask_llama`) — nothing else changes.

> **Status note:** TM/Trainer data is currently **simulated** (`chat_bot/data_global/*_sim.csv`, deterministic seed). Swapping to real data = Phase C.

---

## 4. End-to-end data story (for John)

1. **Classes in Excel** — you keep defining classes in `events.xlsx`; each row = one class.
2. **Auto links + QR** — the app makes a unique link and QR per class for flyers/emails.
3. **Dealer self-registration** — scan/click → clean per-class page → register the team in under a minute.
4. **Clean roster** — every signup writes into `registrations.xlsx` in your current sheet's shape.
5. **Intelligent assistant** — the chat sits over these same tables: Public (classes/seats), TM (dealer progress), Trainer (rosters/attendance), all on a local Llama.

---

## 5. Technical blueprint (for future builds)

### 5.1 Stack & principles
- **Python standard library** HTTP server (`server.py` → `ThreadingHTTPServer`). No Node, no framework, no build step.
- Deps (in `.venv/`): `openpyxl` (xlsx), `segno` (QR), `PyYAML` (chat config). Ollama is external.
- **Config-driven paths:** `config.py` is the single source for paths + the export-column contract. `DB_BACKEND` switch already anticipates a future Postgres swap.
- **The chat is a sandbox:** everything under `chat_bot/` reads/writes only inside `chat_bot/`, enforced by `chat_src/paths.py` (raises `SandboxError` on escape).

### 5.2 Architecture boundary rules (enforced, machine-checked ✅)
1. **Only `AI_oLLama/`** talks to a Llama runtime.
2. **Only `chat_core/`** imports `AI_oLLama`.
3. The app (`src/`) calls **only `chat_core`** (via `src/chat_bridge.py`) — never `AI_oLLama`/`chat_rag` directly.
4. Data lives only in `data_*` and `chat_rag/`; everything else is code/config.

### 5.3 Request flow (one chat turn)
```
browser (static/chat.js)
  └─ POST /api/chat_bot  { session_id, message, mode, tm_key?, trainer_code? }
       └─ src/routes.py  → src/chat_bridge.py  (adds chat_bot/ to sys.path)
            └─ chat_core.router.handle_message(session_id, message, mode, tm_key, trainer_code)
                 ├─ auth? tm_auth / trainer_auth → build snapshot (tm_stats / trainer_stats)
                 ├─ gather CONTEXT:  answer_public | answer_tm | answer_trainer
                 ├─ AI_oLLama.ask_llama([system+CONTEXT, history…, user])
                 │      └─ on LlamaUnavailable → rule-based fallback text
                 └─ persist session (chat_core/state.py)  → returns reply string
       └─ bridge returns { reply, mode, tm_id, trainer_id, display_name }
```

---

## 6. File map (what each piece does)

### Registration app (root + `src/`)
| Path | Role |
|---|---|
| `server.py` | stdlib entry point; wires repo + `Handler`, serves on :8000 |
| `config.py` | paths, export-column contract, tunables, `DB_BACKEND` switch |
| `src/routes.py` | HTTP routing: pages, `/api/event(s)`, `/api/register`, `/api/export.xlsx`, `/api/chat_bot` |
| `src/catalog.py` | reads `events.xlsx`, derives `date_info`, event views |
| `src/registrations.py` | validates a submission → structured registration |
| `src/db/` | repository layer (SQLite today) |
| `src/export.py` | writes/serves `registrations.xlsx` |
| `src/qr_pack.py` | printable QR sheet HTML |
| `src/email_campaign.py` | reminder pipeline: render 7/3/1-day HTML emails + .ics, schedule, simulated sender |
| `email_demo.py` | email-campaign demo console (generate / send / status / preview / seed) |
| `src/chat_bridge.py` | **the only link** between app and `chat_bot/` (imports only `chat_core`) |
| `static/index.html` · `app.js` · `styles.css` · `chat.js` | landing page + chat widget |
| `data/events.xlsx` | class catalog (John edits) |

### Chat package (`chat_bot/`)
| Path | Role |
|---|---|
| `AI_oLLama/llm_client.py` | **only** Llama caller: `ask_llama`, `is_available`, `system_prompt`; raises `LlamaUnavailable` |
| `AI_oLLama/model_config.yaml` | model (`llama3.2:3b`), temp, base_url, limits |
| `AI_oLLama/prompts.yaml` | system prompts per mode + safety rules |
| `chat_core/router.py` | **the entrypoint** `handle_message(...)`; mode resolution + fallback |
| `chat_core/answer_public.py` | builds CONTEXT + fallback from class index |
| `chat_core/answer_tm.py` | builds CONTEXT + fallback from TM snapshot |
| `chat_core/answer_trainer.py` | builds CONTEXT + fallback from trainer snapshot |
| `chat_core/tm_auth.py` · `tm_stats.py` | TM key validation + per-TM snapshot |
| `chat_core/trainer_auth.py` · `trainer_stats.py` | trainer code validation + per-trainer snapshot |
| `chat_core/state.py` | per-session memory (mode, connection, last N turns) |
| `chat_rag/ingest.py` | load `data_global/*.csv` → typed records |
| `chat_rag/build_index.py` | build `index_classes.json` + `index_dealers.json` |
| `chat_rag/retrieve.py` | keyword/branch/topic/seat filtering |
| `chat_rag/seed_sim_data.py` | regenerate simulated CSVs (seed=42) + rebuild indexes |
| `chat_src/paths.py` | **sandbox**: all path resolution stays under `chat_bot/` |
| `chat_src/config.py` · `models.py` | YAML loaders + dataclasses |
| `chat_config/tm_keys.yaml` · `trainer_codes.yaml` · `settings.yaml` · `rag_config.yaml` | config (keys, topics, thresholds) |
| `data_global/` | canonical sim tables (classes, dealers, registrations) |
| `data_temp/{sessions,tm_cache,trainer_cache}/` | runtime snapshots + session logs |
| `temp_1..3/` | per-TM sandbox scratch (e.g. `dealers_summary.csv`) |
| `demo.py` | runs all three modes with no server |

---

## 7. How to run / operate

```sh
# 1. Web server (deps in .venv: openpyxl, segno, pyyaml)
cd <project root>
./.venv/bin/python server.py            # http://localhost:8000

# 2. Local Llama (optional — chat falls back to rule-based without it)
brew install ollama                      # one time
brew services start ollama               # background service
ollama pull llama3.2:3b                  # ~2GB, one time
curl -s http://localhost:11434/api/tags  # verify model present

# 3. Standalone chat demo (no server)
cd chat_bot && ../.venv/bin/python demo.py

# 4. Regenerate simulated data + indexes
cd chat_bot && ../.venv/bin/python -m chat_rag.seed_sim_data

# 5. Email campaign demo (no server) — 5 seed, 1 generate, 2 send (type a date)
./.venv/bin/python email_demo.py
```

**API contract** — `POST /api/chat_bot` (alias `/api/chat`):
```json
request:  { "session_id": "...", "message": "...", "mode": "public|tm|trainer",
            "tm_key": "optional", "trainer_code": "optional" }
response: { "reply": "...", "mode": "...", "tm_id": "...", "trainer_id": "...",
            "display_name": "Connected name or empty" }
```

---

## 8. Checkpoints (progress log)

- ✅ **CP1** — Registration app: Excel catalog, per-class pages, John-format roster, QR workflow. *(pre-existing, verified running)*
- ✅ **CP2** — Chat scaffold sandboxed under `chat_bot/`; rule-based Public + TM answers; `/api/chat` + floating widget.
- ✅ **CP3** — Re-architected to spec: `AI_oLLama` / `chat_core` / `chat_rag` with enforced boundaries; rule-based fallback; per-session memory.
- ✅ **CP4** — Local Llama live (Ollama `llama3.2:3b`); chat gives real reasoned answers, grounded in CONTEXT.
- ✅ **CP5** — Trainer mode added (codes, snapshot, rosters/attendance); 3-mode UI toggle, minimize/close + minimized bar; mode switch resets the conversation.
- ✅ **CP6** (2026-06-11) — Public URL live: **https://jw.caitryapps.com** (named Cloudflare tunnel `jw` → localhost:8000; domain caitryapps.com on Cloudflare Registrar). QR pack renders public https URLs (Host + X-Forwarded-Proto). Mac must stay awake while demoing.
- ✅ **CP7a** (2026-06-11) — REAL data wired in:
  - **Registration**: `data/dealers.xlsx` (205 program dealers from "2026 Program Dealers.xlsx") feeds a company typeahead (`/api/dealers` + datalist). On submit the server resolves Account # + Territory Manager from the sheet (`src/dealers.py`) — the form never asks for them. Unknown companies still register (account/TM blank).
  - **Access codes**: `tools/make_codes.py` reads `data/employees.xlsx` → 21 real TM keys (TMs with program dealers only), 5 trainer codes (John Ward + 4 Field Service Reps), 7 leadership all-territory keys (CEO/President/RSMs). Handout: `data/access_codes.xlsx` (git-ignored — codes + PII never committed; chat yaml/csv outputs ignored too). Deterministic codes — rerunning never reshuffles.
  - **Chat**: TM mode shows each TM's REAL dealers (scoping: dealer `branch` column carries the TM's name). Training history still simulated over the real dealers.
- ✅ **CP7.5** (2026-06-11) — **ADMIN-HUB** at `/admin` (`static/admin_hub.html` + `src/admin_hub.py` + `/api/admin-hub/*`): code login reusing the chat codes (TRAIN-→teacher, EXEC-→staff view-all w/ region filter, TM-→view-only scoped to `registrations.territory_manager`). Teacher gets an editable grade sheet (attended/pass-fail/score/comment) with a **deliberately disabled gray "SUBMIT CLASS INFO" button** — persistence of grades is the next paid phase. Read-only against live DB; no schema changes. Catalog refreshed to 10 summer classes across 8 regions (`tools/make_events_2026.py` — rewrites events.xlsx + classes_sim.csv; then rerun make_codes.py + build_index).
- ✅ **CP7e** (2026-07-13) — **MASTER workbook = single source.** `_data_in/MASTER COPY  Training Hub Info Phase 1.xlsx` (3 tabs) is now the ONE human-edited file; `tools/build_from_master.py` compiles it → `OFFICIAL_CLASS_SCHEDULE.xlsx` + `dealers.xlsx` (224) + `employees.xlsx` (169) + `classes_sim.csv`, then `make_codes.py` (18 TM keys / 5 trainer / 7 leadership) + `sync_chat_from_db.py` (chat→zero) + `build_index`. Real catalog now 72 classes (69 active + 3 internal), fixing gaps the hand-built version missed (Aug 18 Daikin onboarding, Daikin ductless/FIT, full dehumidifier tour, RUUD COMMERCIAL PRODUCT). Also: earlier seeded-demo registrations (135, all for retired classes) wiped to zero — `registrations.xlsx` honestly empty until real signups. Full decision: `docs/ADR-master-workbook.md`. Runtime shapes unchanged.
- ✅ **CP7d** (2026-07-13) — **ONE official catalog.** All classes unified into `data/OFFICIAL_CLASS_SCHEDULE.xlsx` (sheets: events / branches / closures), now the single source `config.EVENTS_XLSX` points to (was `data/events.xlsx`). Built by `tools/make_official_schedule.py`, which merges John's typed Fall 2026 list with the OCR'd `_data_in/M&A Training Schedule for Hub.pdf` (Outlook "Tech Team" calendar). PDF filled in blank times (Heat Pump AL cities 9-2, TN cities 8-1) and added a **Samsung** product week (11/30–12/4, cities/times TBD). 65 classes, 20 branches, 3 company closures. TBD/tentative flags preserved (21 time-TBD, 11 trainer-TBD, 12 Business examples). Old catalogs + `make_events_2026.py`/`make_events_fall2026.py` archived to `_archive_data/superseded_catalogs/`. OCR method: pymupdf render @200dpi + 180° rotate (scanned upside-down) → visual read.
- ✅ **CP7c** (2026-07-13) — **Real data pass.** (1) Data audit: unused/raw/fake files moved to `_archive_data/` (git-ignored, see its ARCHIVE_MANIFEST.md). (2) Chat de-faked: `tools/sync_chat_from_db.py` rebuilds `registrations_sim.csv` from the REAL `registrations.db` (223 rows, honest pending state) — no more seed-42 fiction. (3) **Real Fall 2026 catalog** replaces the summer demo: `tools/make_events_fall2026.py` encodes John's schedule (64 class-instances, 8 topics, 2 tracks) → `data/events.xlsx` + human-readable `data/fall_2026_schedule.xlsx` master + `classes_sim.csv`. Unknowns kept honest (Time TBD / Trainer TBD flags; Business classes = tentative examples). NOTE: the 135 June demo registrations now reference retired event_ids (chat TM history shows blank topics for them); real Fall classes start at zero signups. `make_events_2026.py` is superseded.
- ⬜ **CP7b** — Real training history: grade persistence (enable the submit button: ALTER registration_attendees + save endpoint) + trainer logger / attendance. NOTE: `registration_attendees` ALREADY has attended/passed/score/comment/graded_by/graded_at columns with data — verify what's wired before treating as unbuilt.
- ⬜ **CP8** — (optional) 24/7 hosting: small VPS (same stack), re-point jw.caitryapps.com; decide chat LLM (fallback / hosted / VPS Ollama).

---

## 9. Roadmap (3 phases — the slide)

**Phase A — Finish dealer landing (short term)**
- "Why train with us?" / partner-level copy block.
- Lightweight source tracking ("where did this registration come from" — QR, email, etc.).

**Phase B — Training Assistant, local Llama** ✅ *largely done*
- Chat wired to the sandboxed brain under `chat_bot/`. ✅
- Simulated TM + Trainer data. ✅
- Local Llama integration (no data leaves the machine). ✅
- Remaining: polish prompts, optional deterministic mode for list-style answers.

**Phase C — Territory Manager & Trainer tools (real data)**
- Real TM keys + per-TM history snapshots.
- Real trainer codes + class rosters.
- Optional: hosted deployment (Vercel + Postgres + hosted LLM) for a public URL.

---

## 10. Known notes / decisions
- **Two different "levels" — do NOT conflate (client clarification 2026-06-17):**
  - **Class / training level** (`Level 1/2/3` in `make_events_2026.py` `LEVELS`, `classes_sim.csv.level`, chat "behind on Level 1") = difficulty/progression of the *course*. This is the only one tied to *passed classes*.
  - **Dealer level** = the dealer's *business standing / relationship value*, NOT classes passed:
    - **Level 1 = leverage dealer**
    - **Level 2 = big dealer**
    - **Level 3 = transactional dealer**
    The sim `tier` field (Bronze/Silver/Gold in `seed_sim_data.py`) is a placeholder, not this. When dealer-level is wired to real data it should map to leverage/big/transactional, separate from class level. Noted only — page intentionally left unchanged.
- **LLM wording varies run-to-run** (it's a model, not a template) — always grounded in real data. Option exists to force deterministic fallback for list-style TM/Trainer answers if a steady demo is preferred.
- **Demo link tradeoff:** a tunnel needs *your* machine on (server + Ollama). It's for "try it now," not permanent hosting.
- **Privacy is the deploy fork:** local Llama keeps dealer data in-house; a public site means a hosted LLM (data leaves). Decide before Phase C.
- **`.venv` matters:** run with `./.venv/bin/python`, not bare `python3` (deps live in the venv).
