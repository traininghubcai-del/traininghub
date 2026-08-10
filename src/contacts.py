"""Who to call — per branch, per region.

Phone numbers are NOT in any of the source workbooks (checked all of them), and
inventing them would be worse than showing nothing: a dealer calls a wrong number
and the class looks unprofessional. So this module does two things:

  1. Derives the real contacts we DO have — each branch's Regional Manager and
     the class's own instructor — straight from the master workbook and catalog.
  2. Reads phone numbers from data/branch_contacts.json, which is pre-seeded with
     every branch and blank numbers for John to fill in. A branch with no number
     simply shows its people, never a placeholder or a wrong number.

Editing that one file is the whole workflow — no code change, no redeploy.
"""
import json
import re

from config import DATA

STORE = DATA / "branch_contacts.json"

# Regional Managers by territory, from the MASTER "Reg. Mgr …" sheets. Branch
# names there are shorthand ("FT SMITH", "NESBIT. MS") so they are matched
# loosely against the catalog's branch/region values.
REGIONS = {
    "Arkansas": {
        "manager": "Todd Compton",
        "branches": ["Ft. Smith", "Hot Springs", "Jonesboro", "Little Rock", "Springdale"],
    },
    "West Tennessee": {
        "manager": "Wade Willis",
        "branches": ["Jackson", "Memphis", "Nesbit"],
    },
    "Central TN / Huntsville": {
        "manager": "Randy Vaught",
        "branches": ["Columbia", "Huntsville", "Murfreesboro", "Nashville"],
    },
    "Alabama & Florida": {
        "manager": "Todd Lynn",
        "branches": ["Birmingham", "Mobile", "Pensacola"],
    },
    "East Tennessee": {
        "manager": "Greg Snyder",
        "branches": ["Chattanooga", "Cookeville", "Johnson City", "Knoxville"],
    },
}


def _norm(s):
    """'410- Little Rock' / 'Little Rock, AR' -> 'little rock'."""
    s = re.sub(r"^\s*\d+\s*[-–]\s*", "", str(s or ""))   # strip a branch number
    s = re.sub(r",\s*[A-Z]{2}\s*$", "", s.strip())        # strip trailing state
    return re.sub(r"[^a-z ]", "", s.lower()).strip()


def region_for(branch="", region=""):
    """Which territory a class belongs to. Returns (territory, manager) or ("","")."""
    for key in (branch, region):
        n = _norm(key)
        if not n:
            continue
        for terr, cfg in REGIONS.items():
            if any(_norm(b) == n or _norm(b) in n or n in _norm(b) for b in cfg["branches"]):
                return terr, cfg["manager"]
    return "", ""


def _load():
    if not STORE.exists():
        return {}
    try:
        return json.loads(STORE.read_text() or "{}")
    except (ValueError, OSError):
        return {}


def branch_phone(branch="", region=""):
    """The branch's own number, or "" when it hasn't been filled in yet."""
    book = _load()
    for key in (branch, region):
        n = _norm(key)
        if not n:
            continue
        for name, rec in book.items():
            if _norm(name) == n:
                return str(rec.get("phone", "") or "").strip()
    return ""


def support_for(event):
    """The contact block shown on a class page and printed on its letter.

    Everything here is real: the branch's own number when John has entered one,
    that territory's Regional Manager, and the class's instructor.
    """
    branch = str(event.get("branch", "") or "")
    region = str(event.get("region", "") or "")
    terr, manager = region_for(branch, region)
    return {
        "branch": branch,
        "branch_label": re.sub(r"^\s*\d+\s*[-–]\s*", "", branch).strip() or region,
        "region": region,
        "territory": terr,
        "regional_manager": manager,
        "phone": branch_phone(branch, region),
        "trainer": str(event.get("trainer", "") or "").strip(),
    }


def seed(branches):
    """Create data/branch_contacts.json with every branch and a blank number,
    so filling it in is the only step. Never overwrites an existing entry."""
    book = _load()
    added = 0
    for b in branches:
        label = re.sub(r"^\s*\d+\s*[-–]\s*", "", str(b)).strip()
        if not label or label in book:
            continue
        terr, mgr = region_for(b, label)
        book[label] = {"phone": "", "territory": terr, "regional_manager": mgr}
        added += 1
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(book, indent=2, sort_keys=True))
    return added, len(book)


def set_phone(branch, phone):
    """Save one branch's number. Blank clears it back to 'call your branch'."""
    label = re.sub(r"^\s*\d+\s*[-\u2013]\s*", "", str(branch or "")).strip()
    if not label:
        return {"ok": False, "error": "Missing branch."}
    phone = str(phone or "").strip()
    if phone and len(re.sub(r"\D", "", phone)) < 10:
        return {"ok": False, "error": "That doesn't look like a full phone number."}
    book = _load()
    rec = book.get(label)
    if rec is None:
        terr, mgr = region_for(branch, label)
        rec = {"phone": "", "territory": terr, "regional_manager": mgr}
    rec["phone"] = phone
    book[label] = rec
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(book, indent=2, sort_keys=True))
    return {"ok": True, "branch": label, "phone": phone,
            "message": f"{label} phone {'saved' if phone else 'cleared'}."}


def all_branches():
    """Everything in the contact book — for an at-a-glance directory."""
    return dict(sorted(_load().items()))
