"""The repository contract every backend implements.

App code depends only on this interface, never on a concrete driver. Swapping
SQLite for Postgres later means writing one new subclass — no caller changes.
"""
from abc import ABC, abstractmethod


class Repository(ABC):
    @abstractmethod
    def init(self):
        """Create tables if they don't exist."""

    @abstractmethod
    def save_registration(self, reg, capacity=None):
        """Persist one structured registration (from registrations.build_registration).

        `capacity`, when given, MUST be enforced inside the same transaction as
        the insert — checking before the call is a race on the last seat.
        Implementations raise their SeatsUnavailable when it would be exceeded.

        Upserts the event cache, company, and each attendee person, computing
        new-vs-returning. Returns a summary dict:
            {registration_id, company_returning, new_count, returning_count,
             attendees: [{name, role, returning}, ...]}
        """

    @abstractmethod
    def all_registrations_flat(self):
        """Return rows in the flat 8-column export shape (keys = config.COLUMNS
        internal names) plus event_id / created_at / returning counts for admin."""

    @abstractmethod
    def class_roster(self, event_id):
        """Return the registrations for one class:
            [{registration_id, company_name, contact_email, num_attending,
              attendees: [{name, role}, ...]}, ...]"""

    @abstractmethod
    def registration_snapshot(self, reg_id):
        """Full record of one registration (including attendee names), or None.
        Captured before deletion so the audit log records what was lost."""

    @abstractmethod
    def delete_registration(self, reg_id):
        """Remove one registration (and its attendees) from the DB. Returns the
        number of registration rows deleted (0 if not found)."""

    @abstractmethod
    def class_grades(self, event_id):
        """One row per student in a class, with grading state — what the FSR
        grading screen and the admin roster both read:
            [{attendee_id, name, role, company_name, contact_email,
              attended, passed, score, comment, graded_by, graded_at}, ...]"""

    @abstractmethod
    def class_closed_at(self, event_id):
        """Timestamp the class was closed out, or "" if it's still open."""

    @abstractmethod
    def mark_class_closed(self, event_id):
        """Close a class: attendance + grades are final. Returns the timestamp."""

    @abstractmethod
    def reopen_class(self, event_id):
        """Undo a close-out so grades can be corrected."""

    @abstractmethod
    def save_grades(self, event_id, grades, graded_by):
        """Persist attendance / score / pass / comment for students in one class.
        `grades` is [{attendee_id, attended, score, passed, comment}, ...].
        Only rows that really belong to this class are written. Returns the
        number of student rows updated."""
