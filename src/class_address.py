"""Class address — a floating overlay on top of the catalog.

BRANCH is the structural attribute. It comes from the tables, it drives the
filters, the TM mapping, the exports and the DB cache, and it is the thing every
system joins on. It lives in the catalog workbook and is edited there.

ADDRESS is not that. A class is usually held at its branch, but sometimes it
moves — a hotel, a dealer's shop, a distributor's training room — and that street
address can change twice before the class happens. Putting it in the workbook
would mean every address correction rewrites a row in the table everyone else
reads from.

So it lives here instead: data/class_address.json, keyed by event_id.

  - Editing an address touches ONLY this file. The workbook is never opened.
  - No address set  -> the class falls back to the workbook's event_location,
    so all 69 existing classes read exactly as they do today.
  - date_info (John's export string) keeps using the workbook's event_location,
    so the registration export contract in config.COLUMNS never shifts under a
    late address edit.

Delete this file and nothing breaks — every class just falls back to its branch
location. That is what "floating" means here.
"""
import json

from config import DATA

STORE = DATA / "class_address.json"


def _load():
    if not STORE.exists():
        return {}
    try:
        return json.loads(STORE.read_text() or "{}")
    except (ValueError, OSError):
        return {}


def _save(d):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=2, sort_keys=True))


def all_addresses():
    """{event_id: address} — one read for callers looping over many classes."""
    return _load()


def get_address(event_id):
    """The override for one class, or "" when none is set."""
    return str(_load().get(str(event_id).strip(), "")).strip()


def resolve(event_id, fallback):
    """Address to show for a class: the override if set, else the catalog's
    event_location. Every display path should go through this."""
    return get_address(event_id) or str(fallback or "").strip()


def set_address(event_id, address):
    """Set (or clear, with an empty string) one class's address. Writes only to
    data/class_address.json — the catalog workbook is not touched."""
    eid = str(event_id).strip()
    if not eid:
        return {"ok": False, "error": "Missing event_id."}
    addr = str(address or "").strip()
    if len(addr) > 300:
        return {"ok": False, "error": "That address is too long (300 characters max)."}

    d = _load()
    if addr:
        d[eid] = addr
    else:
        d.pop(eid, None)          # cleared -> fall back to the branch location
    _save(d)
    return {"ok": True, "address": addr,
            "message": "Class address updated." if addr else "Class address cleared — back to the branch location."}
