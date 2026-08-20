"""M&A Supply — Training Landing Page — local server (Python standard library).

Thin entry point: builds the repository, wires the HTTP handler, starts serving.
All logic lives in src/ (catalog, registrations, export, qr_pack, routes, db).

Run:
    python3 server.py            # http://localhost:8000
    python3 server.py 9000       # custom port

Endpoints:
    GET  /  /class.html        -> landing page (reads ?event= client-side)
    GET  /static/*             -> css / js
    GET  /api/event?id=<slug>  -> one event (display fields + branch list), or not-found
    GET  /api/events           -> all visible events (index list + QR generation)
    GET  /qr-pack[?event=<id>] -> printable QR sheet (Print -> Save as PDF)
    POST /api/register         -> validate + store one registration
    GET  /api/registrations    -> JSON of all registrations (admin view)
    GET  /api/export.xlsx      -> download registrations as .xlsx (exact column order)
"""
import os
import signal
import subprocess
import sys
import time
from http.server import ThreadingHTTPServer

from config import EMAIL_DAILY_SEND, EMAIL_SEND_HOUR
from src.db import get_repository
from src.export import write_registrations_xlsx
from src.routes import Handler


def _free_port(port):
    """If a stale server is still holding `port`, kill it so we can rebind.

    Closing a terminal tab leaves the old server.py running and owning the port,
    which made a fresh start crash with 'Address already in use'. We find the
    listener via lsof and terminate it (gracefully, then hard) — but never touch
    our own PID, so this is safe to call at every startup.
    """
    try:
        out = subprocess.run(["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                             capture_output=True, text=True).stdout
    except FileNotFoundError:
        return  # no lsof (non-mac); SO_REUSEADDR below still helps
    pids = [int(p) for p in out.split() if p.strip().isdigit() and int(p) != os.getpid()]
    for pid in pids:
        print(f"  freeing port {port}: stopping stale server (pid {pid})")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            continue
    if pids:
        time.sleep(0.6)  # let the OS release the socket before we bind


def main():
    # Railway assigns the port via $PORT and routes to the container's external
    # interface. Binding 127.0.0.1 accepts loopback only, so the platform health
    # check never connects and the edge answers 502 — bind 0.0.0.0 instead.
    # Both are overridable; 8080 is the local-dev fallback, never a prod value.
    port = int(sys.argv[1]) if len(sys.argv) > 1 else int(os.environ.get("PORT", 8080))
    host = os.environ.get("HOST", "0.0.0.0")
    repo = get_repository()
    repo.init()
    try:
        write_registrations_xlsx(repo)  # make sure data/registrations.xlsx exists & is current
    except Exception as e:  # noqa: BLE001
        print(f"  warning: couldn't write registrations.xlsx at startup ({e})")

    # The 7/3/1-day reminders, if this deploy is the one that owns them. Started
    # before the server binds so a start-up failure is visible in the deploy log
    # rather than in the first request that happens to trigger mail.
    if EMAIL_DAILY_SEND:
        from src.scheduler import start as start_scheduler
        start_scheduler()
        print(f"  daily reminder run armed for {EMAIL_SEND_HOUR:02d}:00 local time")

    _free_port(port)
    ThreadingHTTPServer.allow_reuse_address = True
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.repo = repo
    print(f"M&A Supply landing page listening on {host}:{port}  (Ctrl+C to stop)")
    print(f"  example class URL:  http://localhost:{port}/?event=nashville-fit-2026-04-29")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
