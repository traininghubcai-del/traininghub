"""Plain dataclasses for the simulated tables. Stdlib only — no pandas.

Each ``from_row`` turns a CSV dict (all-strings) into a typed record so the rest
of the code never re-parses ints/floats. Column names here ARE the CSV headers.
"""
from dataclasses import dataclass, asdict


def _int(v, default=0):
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return default


def _float(v, default=0.0):
    try:
        return float(str(v).strip())
    except (ValueError, TypeError):
        return default


def _bool(v):
    return str(v).strip().lower() in ("yes", "true", "1", "y")


@dataclass
class ClassRow:
    event_id: str
    region: str
    branch: str
    tm_id: str
    topic: str
    level: str
    event_date: str
    start_time: str
    end_time: str
    capacity: int
    seats_taken: int
    seats_remaining: int
    location: str
    trainer_id: str = ""
    trainer_name: str = ""

    @classmethod
    def from_row(cls, r):
        cap = _int(r.get("capacity"))
        taken = _int(r.get("seats_taken"))
        return cls(
            event_id=r.get("event_id", "").strip(),
            region=r.get("region", "").strip(),
            branch=r.get("branch", "").strip(),
            tm_id=r.get("tm_id", "").strip(),
            topic=r.get("topic", "").strip(),
            level=r.get("level", "").strip(),
            event_date=r.get("event_date", "").strip(),
            start_time=r.get("start_time", "").strip(),
            end_time=r.get("end_time", "").strip(),
            capacity=cap,
            seats_taken=taken,
            seats_remaining=_int(r.get("seats_remaining"), cap - taken),
            location=r.get("location", "").strip(),
            trainer_id=r.get("trainer_id", "").strip(),
            trainer_name=r.get("trainer_name", "").strip(),
        )

    def as_dict(self):
        return asdict(self)


@dataclass
class Dealer:
    dealer_id: str
    dealer_name: str
    branch: str
    tm_id: str
    tier: str
    primary_contact: str
    contact_email: str

    @classmethod
    def from_row(cls, r):
        return cls(
            dealer_id=r.get("dealer_id", "").strip(),
            dealer_name=r.get("dealer_name", "").strip(),
            branch=r.get("branch", "").strip(),
            tm_id=r.get("tm_id", "").strip(),
            tier=r.get("tier", "").strip(),
            primary_contact=r.get("primary_contact", "").strip(),
            contact_email=r.get("contact_email", "").strip(),
        )

    def as_dict(self):
        return asdict(self)


@dataclass
class Registration:
    reg_id: str
    event_id: str
    dealer_id: str
    attendee_name: str
    role: str
    branch: str
    tm_id: str
    level: str
    attended: bool
    score: float
    status: str          # Completed | In Progress | No Show
    reg_date: str

    @classmethod
    def from_row(cls, r):
        return cls(
            reg_id=r.get("reg_id", "").strip(),
            event_id=r.get("event_id", "").strip(),
            dealer_id=r.get("dealer_id", "").strip(),
            attendee_name=r.get("attendee_name", "").strip(),
            role=r.get("role", "").strip(),
            branch=r.get("branch", "").strip(),
            tm_id=r.get("tm_id", "").strip(),
            level=r.get("level", "").strip(),
            attended=_bool(r.get("attended")),
            score=_float(r.get("score")),
            status=r.get("status", "").strip(),
            reg_date=r.get("reg_date", "").strip(),
        )

    def as_dict(self):
        return asdict(self)
