"""Validate a submitted form and turn it into a structured registration.

Returns a rich dict (company / contact / attendee list / event snapshot) that the
repository persists across the normalized tables. The flat 8-column export is
rebuilt later from those tables (see src/export.py), so the snapshot fields here
(`date_info`, `attendees_joined`) only need to match John's format.
"""
import re
from datetime import datetime

from config import EMAIL_RE, FILL_TM_FROM_BRANCH, ROLES
from src.catalog import build_date_info, event_cache_row, is_active, load_catalog
from src.dealers import find_dealer

# "Jane Doe (Technician)" -> ("Jane Doe", "Technician"); "Jane Doe" -> ("Jane Doe", "")
_ATTENDEE_RE = re.compile(r"^\s*(?P<name>.*?)(?:\s*\((?P<role>[^()]*)\))?\s*$")


def _normalize_attendees(payload):
    """Prefer the structured attendees_list; fall back to parsing the joined string."""
    raw = payload.get("attendees_list")
    out = []
    if isinstance(raw, list):
        for a in raw:
            name = str((a or {}).get("name", "")).strip()
            role = str((a or {}).get("role", "")).strip()
            if name:
                out.append({"name": name, "role": role if role in ROLES else ""})
        return out
    joined = str(payload.get("attendees", "")).strip()
    if not joined:
        return out
    for part in joined.split(","):
        m = _ATTENDEE_RE.match(part)
        name = (m.group("name") or "").strip()
        role = (m.group("role") or "").strip()
        if name:
            out.append({"name": name, "role": role if role in ROLES else ""})
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
