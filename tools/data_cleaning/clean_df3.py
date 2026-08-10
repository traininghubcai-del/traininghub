"""Clean df3_daiintrainingform2026_data_nashville_428.xlsx.

Field-level validators (`_safe`-wrapped) coerce every cell — bad/garbage values
become pd.NA so no row can crash the run. Before touching the real file, the
pipeline is fuzz-tested with 300 random/chaotic DataFrames; retries up to 5
seeds if anything throws. Writes test.xlsx in the same folder.
"""

from __future__ import annotations

import datetime
import random
import re
import string
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "df3_daiintrainingform2026_data_nashville_428.xlsx"
TARGET = HERE / "test.xlsx"

RAW_COLS = [
    "date_info", "Contact Email", "Company Name", "Account Number",
    "# Attending", "Names of Attendees", "Branch Location:",
    "Territory Manager",
]


def _safe(fn):
    """Wrap a per-cell validator so any exception or NaN-like input → NA."""
    def wrapped(value):
        try:
            if value is None:
                return pd.NA
            if isinstance(value, float) and np.isnan(value):
                return pd.NA
            return fn(value)
        except Exception:
            return pd.NA
    return wrapped


EMAIL_RE = re.compile(r"^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$")
BRANCH_RE = re.compile(r"^\s*(\d{2,4})\s*-\s*([A-Za-z][A-Za-z .'\-]*)\s*$")
TERR_RE = re.compile(r"^[A-Z][A-Z .'\-]*,\s*[A-Z][A-Z .'\-]*$")

# event_info format:
#   "WEDNESDAY, APRIL 29, 2026_9AM- 3PM_ FIT INSTALL & COMMISSIONING _ @ NASHVILLE BRANCH"
# Tolerates extra whitespace around the "_" separators and "_@" / "_ @".
EVENT_RE = re.compile(
    r"^\s*([A-Z]+)\s*,\s*([A-Z]+)\s+(\d{1,2})\s*,\s*(\d{4})\s*_\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*-\s*"
    r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)\s*_\s*"
    r"(.+?)\s*_\s*@\s*(.+?)\s*$"
)

MONTHS = {m.upper(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June",
     "July", "August", "September", "October", "November", "December"], 1)}

VALID_WEEKDAYS = {"MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                  "FRIDAY", "SATURDAY", "SUNDAY"}


def _to_24h(hh, mm, ap):
    hh, mm = int(hh), int(mm or 0)
    if not (1 <= hh <= 12 and 0 <= mm <= 59):
        return None
    if ap == "AM":
        hh = 0 if hh == 12 else hh
    else:
        hh = 12 if hh == 12 else hh + 12
    return f"{hh:02d}:{mm:02d}"


EVENT_FIELDS = ["weekday", "event_date", "start_time", "end_time",
                "topic", "event_location", "event_info_ok"]


def _empty_event():
    d = {k: pd.NA for k in EVENT_FIELDS}
    d["event_info_ok"] = False
    return d


def parse_event_info(raw):
    """Split event_info into structured fields. All-or-nothing on parse;
    weekday is cross-checked against the actual date."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return _empty_event()
    try:
        s = re.sub(r"\s+", " ", str(raw)).strip().upper()
    except Exception:
        return _empty_event()
    m = EVENT_RE.match(s)
    if not m:
        return _empty_event()
    wd, mo, day, yr, sh, smi, sap, eh, emi, eap, topic, loc = m.groups()
    if wd not in VALID_WEEKDAYS or mo not in MONTHS:
        return _empty_event()
    try:
        date = datetime.date(int(yr), MONTHS[mo], int(day))
    except (ValueError, TypeError):
        return _empty_event()
    if not (2000 <= date.year <= 2100):
        return _empty_event()
    start = _to_24h(sh, smi, sap)
    end = _to_24h(eh, emi, eap)
    if start is None or end is None or start >= end:
        return _empty_event()
    actual_wd = date.strftime("%A").upper()
    return {
        "weekday": actual_wd,
        "event_date": date.isoformat(),
        "start_time": start,
        "end_time": end,
        "topic": re.sub(r"\s+", " ", topic).strip(),
        "event_location": re.sub(r"\s+", " ", loc).strip(),
        "event_info_ok": (actual_wd == wd),
    }


@_safe
def v_email(x):
    s = str(x).strip().lower()
    return s if EMAIL_RE.match(s) else pd.NA


@_safe
def v_int(x):
    if isinstance(x, bool):
        return pd.NA
    f = float(x)
    if not np.isfinite(f):
        return pd.NA
    i = int(f)
    return i if i >= 0 else pd.NA


@_safe
def v_text(x):
    s = re.sub(r"\s+", " ", str(x)).strip()
    return s if s else pd.NA


@_safe
def v_title(x):
    s = re.sub(r"\s+", " ", str(x)).strip()
    return s.title() if s else pd.NA


@_safe
def v_branch(x):
    s = re.sub(r"\s+", " ", str(x)).strip()
    m = BRANCH_RE.match(s)
    if not m:
        return s if s else pd.NA
    return f"{m.group(1)}- {m.group(2).strip().title()}"


@_safe
def v_territory(x):
    s = re.sub(r"\s+", " ", str(x)).strip().upper()
    if not s:
        return pd.NA
    return s if TERR_RE.match(s) else s


PLAN = [
    ("date_info",          "event_info",        v_text),
    ("Contact Email",      "contact_email",     v_email),
    ("Company Name",       "company_name",      v_title),
    ("Account Number",     "account_number",    v_int),
    ("# Attending",        "attending_count",   v_int),
    ("Names of Attendees", "attendees",         v_text),
    ("Branch Location:",   "branch",            v_branch),
    ("Territory Manager",  "territory_manager", v_territory),
]


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]
    return df


FINAL_COLS = [
    "event_info", "event_info_ok", "weekday", "event_date",
    "start_time", "end_time", "topic", "event_location",
    "contact_email", "company_name", "account_number",
    "attending_count", "attendees", "branch", "territory_manager",
]


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_columns(df)
    n = len(df)
    out = pd.DataFrame(index=range(n))
    for src, dst, fn in PLAN:
        series = df[src] if src in df.columns else pd.Series([pd.NA] * n)
        out[dst] = series.map(fn)

    parsed_rows = [parse_event_info(v) for v in out["event_info"].tolist()]
    parsed_df = pd.DataFrame(parsed_rows, index=out.index, columns=EVENT_FIELDS)
    for col in EVENT_FIELDS:
        out[col] = parsed_df[col]

    keys = ["contact_email", "company_name", "attendees"]
    mask = out[keys].notna().any(axis=1)
    out = out.loc[mask].reset_index(drop=True)

    for c in ["account_number", "attending_count"]:
        out[c] = out[c].astype("Int64")
    out["event_info_ok"] = out["event_info_ok"].astype("boolean")

    return out[FINAL_COLS]


# ---------- fuzz testing ----------

def _chaos_value(rng: random.Random):
    pool = [
        None, np.nan, float("inf"), float("-inf"),
        "", " ", "  ", "null", "None", "NaN",
        0, -1, 1, 99999999, -1e9, 1e15,
        True, False,
        "not-an-email", "x@y.z", "FOO@BAR.IO  ", "@@@",
        "Acme Inc.", "  multi  space  ", "x" * 400,
        b"bytes", bytearray(b"ba"), ["a", "b"], {"k": 1}, (1, 2),
        rng.randint(-10_000, 1_000_000),
        rng.uniform(-1e9, 1e9),
        "".join(rng.choices(string.printable, k=rng.randint(0, 40))),
        "101- Nashville", "JOHNSON, DREW", "drew@example.com",
        "WEDNESDAY, APRIL 29, 2026_9AM- 3PM_ FIT INSTALL _ @ NASHVILLE BRANCH",
        "MONDAY, FEBRUARY 30, 2026_9AM- 5PM_ X _ @ Y",  # invalid date
        "WEDNESDAY, APRIL 29, 2026_3PM- 9AM_ BAD _ @ Z",  # end < start
    ]
    return rng.choice(pool)


def _make_random_df(rng: random.Random, n: int) -> pd.DataFrame:
    cols = list(RAW_COLS)
    rng.shuffle(cols)
    keep = cols[: max(0, len(cols) - rng.randint(0, 3))]
    data = {c: [_chaos_value(rng) for _ in range(n)] for c in keep}
    return pd.DataFrame(data)


def fuzz(iterations: int, seed: int) -> tuple[bool, str]:
    rng = random.Random(seed)
    expected = set(FINAL_COLS)
    scalar_types = (str, int, np.integer, float, np.floating, bool, np.bool_)
    for i in range(iterations):
        n = rng.randint(0, 60)
        df = _make_random_df(rng, n)
        try:
            out = clean(df)
            assert isinstance(out, pd.DataFrame)
            assert set(out.columns) == expected
            for c in out.columns:
                for v in out[c].tolist():
                    if pd.isna(v):
                        continue
                    if not isinstance(v, scalar_types):
                        return False, f"col={c} bad type: {type(v).__name__}"
        except Exception:
            return False, f"iter={i} n={n}\n{traceback.format_exc()}"
    return True, ""


# ---------- driver ----------

def main() -> int:
    print(f"Source: {SOURCE}")
    print(f"Target: {TARGET}")

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        ok, err = fuzz(iterations=300, seed=0xC0DE + attempt)
        if ok:
            print(f"Fuzz OK on attempt {attempt}.")
            break
        print(f"Fuzz failed attempt {attempt}:\n{err}", file=sys.stderr)
    else:
        print("Cleaner failed fuzz; aborting.", file=sys.stderr)
        return 1

    if not SOURCE.exists():
        print(f"Source missing: {SOURCE}", file=sys.stderr)
        return 2

    raw = pd.read_excel(SOURCE)
    print(f"Read {len(raw)} rows, {len(raw.columns)} cols from source.")
    cleaned = clean(raw)
    print(f"Cleaned -> {len(cleaned)} rows, {len(cleaned.columns)} cols.")

    cleaned.to_excel(TARGET, index=False)
    print(f"Wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
