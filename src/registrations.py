"""Validate a submitted form and turn it into a structured registration.

Returns a rich dict (company / contact / attendee list / event snapshot) that the
repository persists across the normalized tables. The flat 8-column export is
rebuilt later from those tables (see src/export.py), so the snapshot fields here
(`date_info`, `attendees_joined`) only need to match John's format.
"""
import ast
import json
import re
from datetime import datetime

from config import EMAIL_RE, FILL_TM_FROM_BRANCH, ROLES
from src.catalog import build_date_info, event_cache_row, is_active, load_catalog
from src.dealers import find_dealer

# "Jane Doe (Technician)" -> ("Jane Doe", "Technician"); "Jane Doe" -> ("Jane Doe", "")
_ATTENDEE_RE = re.compile(r"^\s*(?P<name>.*?)(?:\s*\((?P<role>[^()]*)\))?\s*$")


# A person's name never contains a bracket or a brace. Apostrophes and hyphens
# do (O'Brien, Smith-Jones), so those are left alone — only the characters that
# can ONLY come from a serialized structure are treated as proof of one.
_STRUCTURAL = re.compile(r"[\[\]{}]")


def _as_people(raw):
    """A list of attendee dicts, or None if `raw` isn't one.

    Accepts the structured list the form posts, and also a JSON or Python-literal
    STRING holding the same thing. A client that stringified its payload used to
    fall through to the comma-splitter below, which chopped
    "[{'name': 'Test Person', 'role': 'Technician'}]" into two fragments and
    stored both as people. One real attendee became two garbage names.
    """
    if isinstance(raw, list):
        return raw
    text = str(raw or "").strip()
    if not text.startswith(("[", "{")):
        return None
    for parse in (json.loads, ast.literal_eval):
        try:
            got = parse(text)
        except (ValueError, SyntaxError, TypeError):
            continue
        if isinstance(got, dict):
            got = [got]
        if isinstance(got, list):
            return got
    return None


def _clean_email(value):
    """A valid address, or "" — an attendee email is optional, so a malformed one
    is dropped rather than failing a registration the dealer already completed.
    The office copy still covers them."""
    text = str(value or "").strip()
    return text if EMAIL_RE.match(text) else ""


def _clean_name(value):
    """A usable name, or "" — anything still carrying structure is dropped.

    This is the last gate before a name reaches the DB. Parsing above should
    mean nothing structural ever gets here; this makes sure that a payload shape
    nobody anticipated writes NO attendee rather than a corrupt one.
    """
    name = str(value or "").strip()
    return "" if _STRUCTURAL.search(name) else name


def _normalize_attendees(payload):
    """Prefer the structured attendees_list; fall back to parsing the joined string."""
    out = []
    people = _as_people(payload.get("attendees_list"))
    if people is None:
        people = _as_people(payload.get("attendees"))
    if people is not None:
        for a in people:
            if not isinstance(a, dict):
                continue
            name = _clean_name(a.get("name"))
            role = str(a.get("role", "")).strip()
            if name:
                out.append({"name": name, "role": role if role in ROLES else "",
                            "email": _clean_email(a.get("email"))})
        return out
    joined = str(payload.get("attendees", "")).strip()
    if not joined:
        return out
    for part in joined.split(","):
        m = _ATTENDEE_RE.match(part)
        name = _clean_name(m.group("name"))
        role = (m.group("role") or "").strip()
        if name:
            # the joined string has never carried an address; blank means
            # "no personal mail for this person", not "unknown"
            out.append({"name": name, "role": role if role in ROLES else "", "email": ""})
    return out


def _join_attendees(attendees):
    return ", ".join(f"{a['name']} ({a['role']})" if a["role"] else a["name"] for a in attendees)


def build_registration(payload):
    """Validate visible fields, derive date_info from the chosen event. TM left blank."""
    event_id = str(payload.get("event_id", "")).strip()
    email = str(payload.get("contact_email", "")).strip()
    company = str(payload.get("company_name", "")).strip()
    branch = str(payload.get("branch", "")).strip()
    attendees = _normalize_attendees(payload)

    events, branch_list, branch_to_tm = load_catalog()
    event = events.get(event_id)
    if event and not is_active(event):
        event = None

    errors = []
    if not event:
        errors.append("This class link is not active.")
    elif str(event.get("event_date", ""))[:10] < str(datetime.now().date()):
        # Past classes are on the master list now so the team can grade them,
        # and an old QR code or bookmark still resolves. Neither may become a
        # way to sign up for a class that already happened.
        errors.append("This class has already taken place — registration is closed.")
    if not EMAIL_RE.match(email):
        errors.append("A valid Work Email is required.")
    if not company:
        errors.append("Company Name is required.")
    if not branch:
        errors.append("Please select your branch.")
    elif branch not in branch_list:
        errors.append("Unknown branch.")
    if not attendees:
        errors.append("Please add at least one attendee.")

    if errors:
        raise ValueError(" ".join(errors))

    # Known program dealer? Resolve account # + TM server-side — the form never
    # asks for them. Unknown companies register fine with both left blank.
    dealer = find_dealer(customer_id=str(payload.get("customer_id", "")).strip(),
                         company_name=company)
    account_number = dealer["customer_id"] if dealer else str(payload.get("account_number", "")).strip()
    territory_manager = (dealer["territory_manager"] if dealer
                         else (branch_to_tm.get(branch, "") if FILL_TM_FROM_BRANCH else ""))
    if dealer:
        company = dealer["company_name"]  # canonical spelling from John's sheet

    return {
        "event_id": event_id,
        "event_cache": event_cache_row(event),
        "date_info": build_date_info(event),
        "contact_email": email,
        "contact_phone": str(payload.get("contact_phone", "")).strip(),
        "company_name": company,
        "account_number": account_number,
        "branch": branch,
        "territory_manager": territory_manager,
        "num_attending": len(attendees),
        "attendees": attendees,                       # [{name, role}, ...]
        "attendees_joined": _join_attendees(attendees),  # snapshot string
        "created_at": datetime.now().isoformat(timespec="seconds"),
    }
