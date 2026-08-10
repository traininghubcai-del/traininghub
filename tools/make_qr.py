"""Generate a QR code per class, pointing at its registration URL.

Each visible event in data/events.xlsx gets a PNG + SVG in qr/, encoding:
    {base}/?event={event_id}

Usage:
    python3 make_qr.py                              # base = http://localhost:8000
    python3 make_qr.py https://training.example.com # use your real domain for production

NOTE: a QR pointing at http://localhost:8000 only works on THIS machine. To send
QRs to dealers, host the app somewhere public and pass that URL as the base.
"""
import sys
from pathlib import Path

import segno

REPO = Path(__file__).resolve().parent.parent  # tools/ -> repo root
sys.path.insert(0, str(REPO))                  # so `src` / `config` import when run from tools/

from src.catalog import public_events  # reuse the live events catalog  # noqa: E402

OUT = REPO / "qr"


def main():
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000").rstrip("/")
    OUT.mkdir(exist_ok=True)
    events = public_events()
    if not events:
        print("No visible events in data/events.xlsx")
        return
    for ev in events:
        url = f"{base}/?event={ev['event_id']}"
        qr = segno.make(url, error="m")
        qr.save(OUT / f"{ev['event_id']}.png", scale=8, border=2)
        qr.save(OUT / f"{ev['event_id']}.svg", scale=8, border=2)
        print(f"{ev['event_id']:<36} -> {url}")
    print(f"\nwrote {len(events)} QR code(s) (PNG + SVG) to {OUT}/")


if __name__ == "__main__":
    main()
