"""HTTP routing only. Business logic lives in the sibling modules; the repository
is reached via self.server.repo (set in server.py)."""
import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from config import STATIC
from src.catalog import event_view, is_active, load_catalog, public_events
from src.dealers import dealer_directory
from src.export import registrations_xlsx_bytes, write_registrations_xlsx
from src.qr_pack import qr_pack_html
from src.db.sqlite_repo import SeatsUnavailable
from src.registrations import build_registration

CONTENT_TYPES = {".html": "text/html", ".css": "text/css", ".js": "application/javascript",
                 ".ico": "image/x-icon", ".svg": "image/svg+xml", ".png": "image/png",
                 ".jpg": "image/jpeg", ".webp": "image/webp"}


class Handler(BaseHTTPRequestHandler):
    server_version = "MASupplyLanding/2.0"

    @property
    def repo(self):
        return self.server.repo

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        if not path.exists() or not path.is_file():
            self.send_error(404, "Not found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPES.get(path.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, must-revalidate")  # always fresh during dev
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, body, content_type, extra_headers=None):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path in ("/", "/index.html", "/class.html"):
            self._send_file(STATIC / "index.html")
        elif path in ("/data-cycle", "/data_cycle"):
            self._send_file(STATIC / "data_cycle.html")
        elif path == "/survey-preview":
            self._send_file(STATIC / "survey_preview.html")
        elif path == "/refresher":
            self._send_file(STATIC / "refresher.html")
        elif path == "/notify-tm":
            body = ("<html><head><meta charset='utf-8'><title>TM notified</title></head>"
                    "<body style='font-family:sans-serif;max-width:480px;margin:14vh auto;"
                    "text-align:center;color:#0a2540'><h2>✓ Your Territory Manager has been notified</h2>"
                    "<p>They now see you on their <b>\"wants a refresher\"</b> list and will reach "
                    "out as soon as a class date opens up. (Demo — the TM notification feed is part "
                    "of the next build phase.)</p><p><a href='/'>&larr; Back to classes</a></p>"
                    "</body></html>").encode("utf-8")
            self._send_bytes(body, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        elif path == "/quiz":
            body = ("<html><head><meta charset='utf-8'><title>Retention quiz</title></head>"
                    "<body style='font-family:sans-serif;max-width:480px;margin:14vh auto;"
                    "text-align:center;color:#0a2540'><h2>📝 Retention quiz</h2>"
                    "<p>The Day-1 / 7 / 30 / 90 retention quizzes are part of the "
                    "<b>next build phase</b>. This link is already wired per student "
                    "per class.</p><p><a href='/'>&larr; Back to classes</a>"
                    "</p></body></html>").encode("utf-8")
            self._send_bytes(body, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
        elif path.startswith("/static/"):
            # allow nested assets (e.g. /static/logos/…) but never escape STATIC
            target = (STATIC / path[len("/static/"):]).resolve()
            if str(target).startswith(str(STATIC.resolve()) + "/"):
                self._send_file(target)
            else:
                self.send_error(404, "Not found")
        elif path == "/api/event":
            try:
                eid = (parse_qs(parsed.query).get("id") or [""])[0].strip()
                events, branches, _ = load_catalog()
                ev = events.get(eid)
                if not ev or not is_active(ev):
                    self._send_json({"found": False, "branches": branches})
                else:
                    from src.contacts import support_for
                    from src.fliers import get_flier
                    self._send_json({**event_view(ev), "branches": branches,
                                     "flier": get_flier(eid),
                                     "support": support_for(ev)})
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"Could not load event: {e}"}, 500)
        elif path == "/qr-pack":
            try:
                host = self.headers.get("Host", "localhost:8000")
                # behind the Cloudflare tunnel the public scheme is https
                scheme = self.headers.get("X-Forwarded-Proto", "http")
                base = f"{scheme}://{host}"
                qs = parse_qs(parsed.query)
                only = (qs.get("event") or [None])[0]
                # ?events=id1,id2 — the exact set the index page is showing, in
                # its on-screen order, so Print reflects the current filter/sort
                picked = [s for s in ((qs.get("events") or [""])[0]).split(",") if s.strip()]
                body = qr_pack_html(base, only_id=only, only_ids=picked or None).encode("utf-8")
                self._send_bytes(body, "text/html; charset=utf-8", {"Cache-Control": "no-store"})
            except Exception as e:  # noqa: BLE001
                self.send_error(500, f"QR pack error: {e}")
        elif path == "/api/hub/modes":
            try:
                from src.hub_modes import mode_list
                self._send_json({"modes": mode_list()})
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"Hub error: {e}"}, 500)
        elif path == "/reminder-letter":
            # one student's reminder letter, built in memory and streamed
            try:
                from src.hub_modes import letter_pdf
                q = parse_qs(parsed.query)
                one = lambda k: (q.get(k) or [""])[0].strip()  # noqa: E731
                pdf, ctx = letter_pdf(self.repo, one("event_id"), one("attendee_id"),
                                      one("mode") or "admin", one("code"))
                if not pdf:
                    self.send_error(403, "Not allowed")
                else:
                    safe = "".join(ch for ch in ctx["student_name"] if ch.isalnum() or ch in " -_").strip()
                    self._send_bytes(pdf, "application/pdf", {
                        "Content-Disposition": f'inline; filename="Reminder-{safe or "student"}.pdf"',
                        "Cache-Control": "no-store"})
            except Exception as e:  # noqa: BLE001
                self.send_error(500, f"Letter error: {e}")
        elif path == "/api/hub/classes":
            try:
                from src.hub_modes import classes_overview
                q = parse_qs(parsed.query)
                result = classes_overview(self.repo, (q.get("mode") or ["admin"])[0].strip(),
                                          (q.get("code") or [""])[0].strip())
                self._send_json(result, 200 if result.get("ok") else 403)
            except Exception as e:  # noqa: BLE001
                self._send_json({"ok": False, "error": f"Hub error: {e}"}, 500)
        elif path == "/api/hub/class":
            # one class, seen through one lens. Restricted data is gated server
            # side — a locked mode never receives the roster at all.
            try:
                from src.hub_modes import class_payload
                q = parse_qs(parsed.query)
                one = lambda k: (q.get(k) or [""])[0].strip()  # noqa: E731
                result = class_payload(self.repo, one("event_id"), one("mode") or "user", one("code"))
                self._send_json(result, 200 if result.get("ok") else
                                (403 if result.get("need_code") else 404))
            except Exception as e:  # noqa: BLE001
                self._send_json({"ok": False, "error": f"Hub error: {e}"}, 500)
        elif path == "/api/hub/flier":
            try:
                from src.fliers import get_flier
                from src.hub_modes import verify
                q = parse_qs(parsed.query)
                one = lambda k: (q.get(k) or [""])[0].strip()  # noqa: E731
                if not verify("admin", one("code")):
                    self._send_json({"ok": False, "error": "Locked.", "need_code": True}, 403)
                else:
                    self._send_json(get_flier(one("event_id")))
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"Flier error: {e}"}, 500)
        elif path.startswith("/flier/"):
            # public: the class page and the print sheet both show the flier
            try:
                from src.fliers import flier_path
                target, ctype = flier_path(path[len("/flier/"):])
                if not target:
                    self.send_error(404, "No flier for this class")
                else:
                    self._send_bytes(target.read_bytes(), ctype,
                                     {"Cache-Control": "no-store, must-revalidate"})
            except Exception as e:  # noqa: BLE001
                self.send_error(500, f"Flier error: {e}")
        elif path == "/api/events":
            try:
                self._send_json({"events": public_events()})
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"Could not load events: {e}"}, 500)
        elif path == "/api/stats":
            # headline numbers for the public page — computed live so they can
            # never drift from the catalog. No invented marketing figures.
            try:
                from src.contacts import REGIONS
                evs = public_events()
                events, branches, _ = load_catalog()
                dealers = 0
                try:
                    dealers = len(dealer_directory())
                except Exception:  # noqa: BLE001
                    pass
                self._send_json({
                    "classes": len(evs),
                    "branches": len(branches),
                    "dealers": dealers,
                    "topics": len({e["topic"] for e in evs if e.get("topic")}),
                    "regions": len(REGIONS),
                })
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"Could not load stats: {e}"}, 500)
        elif path == "/api/dealers":
            try:
                self._send_json({"dealers": dealer_directory()})
            except Exception as e:  # noqa: BLE001
                self._send_json({"error": f"Could not load dealers: {e}"}, 500)
        elif path == "/api/registrations":
            self._send_json({"registrations": self.repo.all_registrations_flat()})
        elif path == "/api/export.xlsx":
            body = registrations_xlsx_bytes(self.repo)
            self._send_bytes(
                body,
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                {"Content-Disposition": 'attachment; filename="registrations.xlsx"'})
        else:
            self.send_error(404, "Not found")

    def do_POST(self):
        post_path = urlparse(self.path).path
        if post_path in ("/api/hub/unlock", "/api/hub/grade", "/api/hub/save-class",
                         "/api/hub/close-class", "/api/hub/reopen-class",
                         "/api/hub/reminders", "/api/hub/create-class",
                         "/api/hub/remove-registration", "/api/hub/flier",
                         "/api/hub/branch-phone", "/api/hub/set-active"):
            try:
                length = int(self.headers.get("Content-Length", 0))
                payload = json.loads(self.rfile.read(length) or b"{}")
                mode = str(payload.get("mode", "")).strip().lower()
                code = str(payload.get("code", ""))
                if post_path.endswith("/unlock"):
                    from src.hub_modes import unlock
                    result = unlock(mode, code)
                elif post_path.endswith("/create-class"):
                    from src.hub_modes import create_class
                    result = create_class(self.repo, mode, code, payload.get("fields") or {})
                elif post_path.endswith("/set-active"):
                    from src.hub_modes import set_class_active
                    result = set_class_active(self.repo, payload.get("event_id", ""),
                                              mode, code, payload.get("active"))
                elif post_path.endswith("/branch-phone"):
                    from src.hub_modes import set_branch_phone
                    result = set_branch_phone(mode, code, payload.get("branch", ""),
                                              payload.get("phone", ""))
                elif post_path.endswith("/remove-registration"):
                    from src.hub_modes import remove_registration
                    result = remove_registration(self.repo, mode, code,
                                                 payload.get("registration_id"))
                elif post_path.endswith("/flier"):
                    from src.fliers import remove_flier, save_flier
                    from src.hub_modes import verify
                    eid = str(payload.get("event_id", "")).strip()
                    if not verify("admin", code):
                        result = {"ok": False, "error": "Locked.", "need_code": True}
                    elif str(payload.get("action", "upload")) == "remove":
                        result = remove_flier(eid)
                    else:
                        result = save_flier(eid, payload.get("filename", ""),
                                            payload.get("data_b64", ""))
                elif post_path.endswith("/reminders"):
                    from src.hub_modes import reminder_letters
                    result = reminder_letters(self.repo, str(payload.get("event_id", "")).strip(),
                                              mode, code,
                                              bool(payload.get("only_attending", True)))
                elif post_path.endswith("/close-class"):
                    from src.hub_modes import close_class
                    result = close_class(self.repo, str(payload.get("event_id", "")).strip(),
                                         mode, code)
                elif post_path.endswith("/reopen-class"):
                    from src.hub_modes import reopen_class
                    result = reopen_class(self.repo, str(payload.get("event_id", "")).strip(),
                                          mode, code)
                elif post_path.endswith("/save-class"):
                    from src.hub_modes import save_class
                    result = save_class(self.repo, str(payload.get("event_id", "")).strip(),
                                        mode, code, payload.get("fields") or {})
                else:
                    from src.hub_modes import save_grades
                    result = save_grades(self.repo, str(payload.get("event_id", "")).strip(),
                                         mode, code, payload.get("grades") or [],
                                         str(payload.get("graded_by", "")).strip())
                self._send_json(result, 200 if result.get("ok") else 403)
            except Exception as e:  # noqa: BLE001
                self._send_json({"ok": False, "error": f"Hub error: {e}"}, 500)
            return
        if post_path not in ("/api/register", "/api/chat", "/api/chat_bot"):
            self.send_error(404, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, json.JSONDecodeError):
            self._send_json({"error": "Invalid request body."}, 400)
            return

        if post_path in ("/api/chat", "/api/chat_bot"):
            try:
                from src.chat_bridge import handle_chat
                result = handle_chat(
                    session_id=str(payload.get("session_id", "anon")),
                    message=str(payload.get("message", "")),
                    mode=str(payload.get("mode", "")),
                    tm_key=str(payload.get("tm_key", "")),
                    trainer_code=str(payload.get("trainer_code", "")),
                )
                self._send_json(result)
            except Exception as e:  # noqa: BLE001
                self._send_json({"reply": f"Chat error: {e}", "mode": "public"}, 500)
            return

        try:
            reg = build_registration(payload)
            cap = int(float(reg["event_cache"].get("capacity") or 0))
        except ValueError as e:
            self._send_json({"error": str(e)}, 400)
            return
        try:
            # capacity is checked inside the write transaction, not before it —
            # two people going for the last seat can't both win
            result = self.repo.save_registration(reg, capacity=cap)
            from src.audit import log
            log("public", "registration.create", reg["event_id"],
                {"company": reg["company_name"], "email": reg["contact_email"],
                 "seats": reg["num_attending"]}, ip=self.client_address[0])
        except SeatsUnavailable as e:
            self._send_json({"error": (
                f"This class is full — only {e.left} seat(s) left of {e.capacity}. "
                "Please reduce your team size or pick another date.")}, 409)
            return
        try:
            write_registrations_xlsx(self.repo)  # refresh the live Excel mirror
        except Exception as e:  # noqa: BLE001 - row is safely in the DB regardless
            print(f"  warning: couldn't refresh registrations.xlsx ({e}); row saved to DB")
        self._send_json({
            "ok": True,
            "returning_count": result["returning_count"],
            "new_count": result["new_count"],
            "message": (f"Thank you — {reg['num_attending']} seat(s) reserved. "
                        f"We'll email a confirmation to {reg['contact_email']}."),
        })

    def log_message(self, fmt, *args):
        print(f"{self.address_string()} - {fmt % args}")
