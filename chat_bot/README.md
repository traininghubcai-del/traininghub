# chat_bot — sandboxed training-data chat (simulated)

A self-contained chat module for M&A Supply training data. **Everything it reads
or writes lives inside `chat_bot/`** — enforced by `chat_src/paths.py`, which
pins every path under this folder and raises `SandboxError` on any attempt to
escape. The rest of the landing-page app is never touched.

For now the data is **100% simulated** (`data_global/*_sim.csv`).

## What it does

- **Public mode** — RAG-style answers about classes & open slots
  (*"What FIT classes are available?"*, *"Any mini split classes in Nashville?"*).
- **TM mode** — a Territory Manager enters an access key and then asks:
  - *"Show my dealers and their training history."*
  - *"Which dealers are behind on Level 1 in my territory?"*

## Run the demo

```sh
cd chat_bot
python -m pip install -r requirements.txt      # PyYAML
python demo.py                                  # generates data + runs both modes
```

Or use the parent project's venv: `../.venv/bin/python demo.py`.

## Layout

```
chat_bot/
  chat_config/        settings.yaml · tm_keys.yaml · rag_config.yaml
  data_global/        classes_sim.csv · registrations_sim.csv · dealers_sim.csv
  data_temp/
    sessions/         per-chat logs (runtime)
    tm_cache/         tm_<id>.json  snapshot rebuilt on each TM login
  temp_1 / temp_2 / temp_3   per-TM sandbox scratch (e.g. dealers_summary.csv)
  chat_src/           paths.py (sandbox) · config.py · models.py · simple_rag.py
  builder_1/          seed_sim_data.py · ingest_sim_data.py · build_rag_index.py
  builder_2/          tm_auth.py · tm_stats.py
  builder_3/          chat_router.py · answer_public.py · answer_tm.py
  demo.py
```

**Rule:** Python lives only in `builder_*` and `chat_src`. Config lives only in
`chat_config`. Global data in `data_global`; per-session / per-TM data in
`data_temp` and `temp_N`. All I/O routes through `chat_src.paths`.

## Demo access keys (simulated)

| Key             | TM            | Branches                          | Sandbox |
|-----------------|---------------|-----------------------------------|---------|
| `NASH-DEMO-KEY` | Nashville     | 101- Nashville, 107- Murfreesboro | temp_1  |
| `COL-DEMO-KEY`  | Columbia      | 125- Columbia, 132- Cookeville    | temp_2  |
| `KNOX-DEMO-KEY` | Knoxville     | 160- Knoxville, 145- Clarksville  | temp_3  |

Edit `chat_config/tm_keys.yaml` to change keys / branch scope.

## Data schema (CSV headers)

- **classes_sim.csv**: `event_id, region, branch, tm_id, topic, level,
  event_date, start_time, end_time, capacity, seats_taken, seats_remaining, location`
- **dealers_sim.csv**: `dealer_id, dealer_name, branch, tm_id, tier,
  primary_contact, contact_email`
- **registrations_sim.csv**: `reg_id, event_id, dealer_id, attendee_name, role,
  branch, tm_id, level, attended, score, status, reg_date`

Regenerate the dataset anytime (deterministic, seed=42):

```sh
cd chat_bot && python -m builder_1.seed_sim_data
```

## Programmatic API

```python
from builder_3 import chat_router

chat_router.handle_message("open mini split classes")        # public
session = chat_router.login("NASH-DEMO-KEY")                 # auth + snapshot
chat_router.handle_message("my dealers", tm_id=session.tm_id) # TM mode
```

## Not yet wired (next step)

The `/api/tm-chat` HTTP endpoint and front-end chat box. The Python API above is
ready to wire into `server.py` when we design that contract.
