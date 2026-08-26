"""SQLite implementation of Repository. The ONLY module that imports sqlite3."""

import sqlite3
from pathlib import Path

from config import COLUMNS, DB_PATH
from src.db.repository import Repository

_SCHEMA = Path(__file__).with_name("schema.sql")


class SeatsUnavailable(Exception):
    """Raised when a registration would push a class past its capacity. Carries
    how many seats were actually left so the caller can say something useful."""

    def __init__(self, left, capacity):
        self.left, self.capacity = left, capacity
        super().__init__(f"only {left} seat(s) left of {capacity}")



class SqliteRepository(Repository):
    def __init__(self, db_path=DB_PATH):
        self.db_path = Path(db_path)

    def _connect(self):
        con = sqlite3.connect(self.db_path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        return con

    def init(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        con = self._connect()
        con.executescript(_SCHEMA.read_text())
        # migrate pre-grading databases (CREATE IF NOT EXISTS won't add new columns)
        for table, col, typ in (
                ("registration_attendees", "attended", "INTEGER"),
                ("registration_attendees", "passed", "INTEGER"),
                ("registration_attendees", "score", "REAL"),
                ("registration_attendees", "comment", "TEXT"),
                ("registration_attendees", "graded_by", "TEXT"),
                ("registration_attendees", "graded_at", "TEXT"),
                ("registration_attendees", "email", "TEXT"),
                ("registrations", "contact_phone", "TEXT")):
            try:
                con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {typ}")
            except sqlite3.OperationalError:
                pass  # column already exists
        con.commit()
        con.close()

    def seats_taken(self, event_id):
        """Live student count for one class — source of truth for capacity checks."""
        con = self._connect()
        n = con.execute(
            """SELECT COUNT(a.id) FROM registration_attendees a
               JOIN registrations r ON a.registration_id = r.id
               WHERE r.event_id = ?""", (event_id,)).fetchone()[0]
        con.close()
        return n

    # --- upserts (get-or-create, returning `existed`) ------------------------
    def _upsert_event(self, con, ev):
        con.execute(
            """INSERT INTO events (event_id, topic, region, branch, event_date,
                   start_time, end_time, event_location, host_label, capacity, synced_at)
               VALUES (:event_id, :topic, :region, :branch, :event_date, :start_time,
                   :end_time, :event_location, :host_label, :capacity, datetime('now'))
               ON CONFLICT(event_id) DO UPDATE SET
                   topic=excluded.topic, region=excluded.region, branch=excluded.branch,
                   event_date=excluded.event_date, start_time=excluded.start_time,
                   end_time=excluded.end_time, event_location=excluded.event_location,
                   host_label=excluded.host_label, capacity=excluded.capacity,
                   synced_at=excluded.synced_at""", ev)

    def _get_or_create_company(self, con, name, account_number, now):
        account_number = account_number or ""
        row = con.execute(
            "SELECT id FROM companies WHERE name = ? AND account_number = ?",
            (name, account_number)).fetchone()
        if row:
            con.execute("UPDATE companies SET last_seen = ? WHERE id = ?", (now, row["id"]))
            return row["id"], True
        cur = con.execute(
            "INSERT INTO companies (name, account_number, first_seen, last_seen) VALUES (?,?,?,?)",
            (name, account_number, now, now))
        return cur.lastrowid, False

    def _get_or_create_person(self, con, name, role, company_id, now, email=""):
        row = con.execute(
            "SELECT id FROM people WHERE name = ? AND company_id IS ?",
            (name, company_id)).fetchone()
        if row:
            # A blank email never erases one we already know. Someone re-registering
            # a tech without retyping their address should not cost that tech their
            # own confirmation next time.
            con.execute("UPDATE people SET last_seen = ?, role = COALESCE(NULLIF(?, ''), role), "
                        "email = COALESCE(NULLIF(?, ''), email) WHERE id = ?",
                        (now, role, email, row["id"]))
            return row["id"], True
        cur = con.execute(
            "INSERT INTO people (name, role, email, company_id, first_seen, last_seen) "
            "VALUES (?,?,?,?,?,?)",
            (name, role, email or None, company_id, now, now))
        return cur.lastrowid, False

    # --- writes --------------------------------------------------------------
    def save_registration(self, reg, capacity=None):
        """Persist one registration.

        `capacity` (when given) is enforced INSIDE the write transaction. Doing
        the seats check in the caller first is a race: two submits for the last
        seat both read "1 free" and both commit. BEGIN IMMEDIATE takes the write
        lock up front, so the count we read cannot change under us.

        Raises SeatsUnavailable when the class would be overbooked.
        """
        now = reg["created_at"]
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            if capacity:
                taken = con.execute(
                    """SELECT COUNT(a.id) FROM registration_attendees a
                       JOIN registrations r ON a.registration_id = r.id
                       WHERE r.event_id = ?""", (reg["event_id"],)).fetchone()[0]
                if taken + reg["num_attending"] > capacity:
                    con.rollback()
                    raise SeatsUnavailable(max(0, capacity - taken), capacity)
            self._upsert_event(con, reg["event_cache"])
            company_id, company_returning = self._get_or_create_company(
                con, reg["company_name"], reg["account_number"], now)
            cur = con.execute(
                """INSERT INTO registrations (event_id, company_id, contact_email, contact_phone,
                       branch, num_attending, territory_manager, date_info, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (reg["event_id"], company_id, reg["contact_email"], reg.get("contact_phone", ""),
                 reg["branch"], reg["num_attending"], reg["territory_manager"], reg["date_info"], now))
            reg_id = cur.lastrowid
            attendees, returning_count = [], 0
            for a in reg["attendees"]:
                email = str(a.get("email") or "").strip()
                person_id, returning = self._get_or_create_person(
                    con, a["name"], a["role"], company_id, now, email)
                con.execute(
                    """INSERT INTO registration_attendees
                           (registration_id, person_id, name, role, email, is_returning)
                       VALUES (?,?,?,?,?,?)""",
                    (reg_id, person_id, a["name"], a["role"], email, int(returning)))
                returning_count += int(returning)
                attendees.append({"name": a["name"], "role": a["role"],
                                  "email": email, "returning": returning})
            con.commit()
        finally:
            con.close()
        return {
            "registration_id": reg_id,
            "company_returning": company_returning,
            "new_count": len(attendees) - returning_count,
            "returning_count": returning_count,
            "attendees": attendees,
        }

    # --- reads ---------------------------------------------------------------
    def all_registrations_flat(self):
        con = self._connect()
        try:
            regs = con.execute(
                """SELECT r.id, r.event_id, r.contact_email, r.branch, r.num_attending,
                          r.territory_manager, r.date_info, r.created_at,
                          c.name AS company_name, c.account_number
                   FROM registrations r
                   LEFT JOIN companies c ON c.id = r.company_id
                   ORDER BY r.id""").fetchall()
            out = []
            for r in regs:
                atts = con.execute(
                    "SELECT name, role, is_returning FROM registration_attendees "
                    "WHERE registration_id = ? ORDER BY id", (r["id"],)).fetchall()
                joined = ", ".join(f"{a['name']} ({a['role']})" if a["role"] else a["name"]
                                   for a in atts)
                returning = sum(a["is_returning"] or 0 for a in atts)
                row = {
                    "date_info": r["date_info"] or "",
                    "contact_email": r["contact_email"] or "",
                    "company_name": r["company_name"] or "",
                    "account_number": r["account_number"] or "",
                    "num_attending": str(r["num_attending"] if r["num_attending"] is not None else ""),
                    "attendees": joined,
                    "branch": r["branch"] or "",
                    "territory_manager": r["territory_manager"] or "",
                    # admin extras (ignored by the 8-column export)
                    "id": r["id"],
                    "event_id": r["event_id"] or "",
                    "created_at": r["created_at"] or "",
                    "returning_count": returning,
                    "new_count": len(atts) - returning,
                }
                out.append(row)
            return out
        finally:
            con.close()

    def _class_log(self, con):
        con.execute("""CREATE TABLE IF NOT EXISTS class_log (
                         event_id TEXT PRIMARY KEY, surveys_sent_at TEXT)""")
        try:                                   # older DBs won't have closed_at yet
            con.execute("ALTER TABLE class_log ADD COLUMN closed_at TEXT")
        except sqlite3.OperationalError:
            pass

    def class_closed_at(self, event_id):
        con = self._connect()
        try:
            self._class_log(con)
            row = con.execute("SELECT closed_at FROM class_log WHERE event_id = ?",
                              (event_id,)).fetchone()
            return (row["closed_at"] if row else "") or ""
        finally:
            con.close()

    def mark_class_closed(self, event_id):
        from datetime import datetime
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        con = self._connect()
        try:
            self._class_log(con)
            con.execute("""INSERT INTO class_log (event_id, closed_at) VALUES (?,?)
                           ON CONFLICT(event_id) DO UPDATE SET
                             closed_at = excluded.closed_at""", (event_id, stamp))
            con.commit()
            return stamp
        finally:
            con.close()

    def reopen_class(self, event_id):
        con = self._connect()
        try:
            self._class_log(con)
            con.execute("UPDATE class_log SET closed_at = NULL WHERE event_id = ?", (event_id,))
            con.commit()
        finally:
            con.close()

    def class_grades(self, event_id):
        con = self._connect()
        try:
            rows = con.execute(
                """SELECT a.id AS attendee_id, a.name, a.role, a.is_returning,
                          a.attended, a.passed, a.score, a.comment,
                          a.graded_by, a.graded_at, a.email AS attendee_email,
                          r.contact_email, r.branch,
                          c.name AS company_name
                   FROM registration_attendees a
                   JOIN registrations r ON a.registration_id = r.id
                   LEFT JOIN companies c ON c.id = r.company_id
                   WHERE r.event_id = ?
                   ORDER BY c.name, a.name""", (event_id,)).fetchall()
            return [{
                "attendee_id": r["attendee_id"],
                "name": r["name"] or "",
                "role": r["role"] or "",
                "company_name": r["company_name"] or "",
                # the student's own address, when they gave one — this is who got
                # the personal confirmation, and staff need to see that it exists
                "email": r["attendee_email"] or "",
                "contact_email": r["contact_email"] or "",
                "branch": r["branch"] or "",
                "is_returning": bool(r["is_returning"]),
                "attended": r["attended"],
                "passed": r["passed"],
                "score": r["score"],
                "comment": r["comment"] or "",
                "graded_by": r["graded_by"] or "",
                "graded_at": r["graded_at"] or "",
            } for r in rows]
        finally:
            con.close()

    def save_grades(self, event_id, grades, graded_by):
        from datetime import datetime
        now = datetime.now().isoformat(timespec="seconds")
        con = self._connect()
        try:
            # only touch students who really belong to this class
            valid = {r[0] for r in con.execute(
                """SELECT a.id FROM registration_attendees a
                   JOIN registrations r ON a.registration_id = r.id
                   WHERE r.event_id = ?""", (event_id,)).fetchall()}
            n = 0
            for g in grades:
                if g["attendee_id"] not in valid:
                    continue
                con.execute(
                    """UPDATE registration_attendees
                       SET attended=?, passed=?, score=?, comment=?, graded_by=?, graded_at=?
                       WHERE id=?""",
                    (g["attended"], g["passed"], g["score"], g["comment"],
                     graded_by, now, g["attendee_id"]))
                n += 1
            con.commit()
            return n
        finally:
            con.close()

    def class_roster(self, event_id):
        con = self._connect()
        try:
            regs = con.execute(
                """SELECT r.id, r.contact_email, r.num_attending, r.created_at,
                          c.name AS company_name
                   FROM registrations r
                   LEFT JOIN companies c ON c.id = r.company_id
                   WHERE r.event_id = ? ORDER BY r.id""", (event_id,)).fetchall()
            out = []
            for r in regs:
                atts = con.execute(
                    "SELECT name, role FROM registration_attendees "
                    "WHERE registration_id = ? ORDER BY id", (r["id"],)).fetchall()
                out.append({
                    "registration_id": r["id"],
                    "company_name": r["company_name"] or "",
                    "contact_email": r["contact_email"] or "",
                    "num_attending": r["num_attending"],
                    "created_at": r["created_at"] or "",
                    "attendees": [{"name": a["name"], "role": a["role"] or ""} for a in atts],
                })
            return out
        finally:
            con.close()

    def registration_snapshot(self, reg_id):
        """Everything about a registration, captured BEFORE it is deleted so the
        audit entry records what was actually lost."""
        con = self._connect()
        try:
            r = con.execute(
                """SELECT r.id, r.event_id, r.contact_email, r.branch, r.num_attending,
                          r.created_at, c.name AS company_name
                   FROM registrations r LEFT JOIN companies c ON c.id = r.company_id
                   WHERE r.id = ?""", (reg_id,)).fetchone()
            if not r:
                return None
            names = [a["name"] for a in con.execute(
                "SELECT name FROM registration_attendees WHERE registration_id = ?", (reg_id,))]
            return {**dict(r), "attendees": names}
        finally:
            con.close()

    def delete_registration(self, reg_id):
        con = self._connect()
        try:
            con.execute("PRAGMA foreign_keys = OFF")
            con.execute("DELETE FROM registration_attendees WHERE registration_id = ?", (reg_id,))
            cur = con.execute("DELETE FROM registrations WHERE id = ?", (reg_id,))
            con.commit()
            return cur.rowcount
        finally:
            con.close()


# Sanity check at import: the export keys we produce must cover the contract.
_PRODUCED = {"date_info", "contact_email", "company_name", "account_number",
             "num_attending", "attendees", "branch", "territory_manager"}
assert {c for _, c in COLUMNS} <= _PRODUCED, "export columns drifted from repo output"
