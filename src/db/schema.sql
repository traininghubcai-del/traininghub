-- Normalized registration store.
-- events.xlsx remains the editable catalog; `events` here is a synced cache so
-- registrations can reference a stable event row.

CREATE TABLE IF NOT EXISTS companies (
  id             INTEGER PRIMARY KEY,
  name           TEXT NOT NULL,
  account_number TEXT NOT NULL DEFAULT '',
  first_seen     TEXT,
  last_seen      TEXT,
  UNIQUE(name, account_number)
);

CREATE TABLE IF NOT EXISTS people (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL,            -- attendee full name as typed
  role        TEXT,
  email       TEXT,                     -- optional today; future per-attendee identity
  company_id  INTEGER REFERENCES companies(id),
  first_seen  TEXT,
  last_seen   TEXT,
  UNIQUE(name, company_id)              -- returning attendee = same name at same company
);

CREATE TABLE IF NOT EXISTS events (     -- cache synced from events.xlsx
  event_id       TEXT PRIMARY KEY,      -- slug
  topic          TEXT,
  region         TEXT,
  branch         TEXT,
  event_date     TEXT,
  start_time     TEXT,
  end_time       TEXT,
  event_location TEXT,
  host_label     TEXT,
  capacity       TEXT,
  synced_at      TEXT
);

CREATE TABLE IF NOT EXISTS registrations (
  id                INTEGER PRIMARY KEY,
  event_id          TEXT REFERENCES events(event_id),
  company_id        INTEGER REFERENCES companies(id),
  contact_person_id INTEGER REFERENCES people(id),  -- reserved for future use
  contact_email     TEXT NOT NULL,
  contact_phone     TEXT,
  branch            TEXT,                            -- registrant's selected branch
  num_attending     INTEGER,
  territory_manager TEXT,
  date_info         TEXT,                            -- snapshot of derived label
  created_at        TEXT
);

CREATE TABLE IF NOT EXISTS registration_attendees (
  id              INTEGER PRIMARY KEY,
  registration_id INTEGER REFERENCES registrations(id) ON DELETE CASCADE,
  person_id       INTEGER REFERENCES people(id),
  name            TEXT,
  role            TEXT,
  is_returning    INTEGER,         -- 0 = new person, 1 = seen before (same company)
  -- per-student grading (filled by trainers in the admin hub; all NULL = ungraded)
  attended        INTEGER,         -- 0/1
  passed          INTEGER,         -- 0/1
  score           REAL,            -- numeric grade
  comment         TEXT,            -- trainer notes
  graded_by       TEXT,            -- trainer_id
  graded_at       TEXT             -- ISO timestamp
);
