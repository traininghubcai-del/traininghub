"""Per-class custom flier: upload, store, serve.

Some classes ship with their own marketing flier (the Daikin-style PROOF sheets
John gets from the vendor). When one exists for a class it replaces nothing —
it rides *alongside* the generated class page, shown between the class banner
and the registration form. Classes without one look exactly as they always have.

Storage is deliberately dumb so it survives a catalog rebuild: the image/PDF
lands in data/fliers/<event_id><ext> and a small JSON index remembers the
original filename, size and upload date. Both are git-ignored (generated), and
the catalog workbook is never touched — a flier is presentation, not schedule
data, so it must not fight the single-catalog rule in
docs/ADR-classes-catalog.md.

Uploads arrive as base64 inside the normal JSON write path (the stdlib server
has no multipart parser, and `cgi` was removed in Python 3.13), gated by the
same Edits & Updates code as every other write in src/manage.py.
"""
import base64
import binascii
import json
import re
from datetime import datetime

from config import DATA

DIR = DATA / "fliers"
INDEX = DIR / "_index.json"

MAX_BYTES = 8 * 1024 * 1024          # 8 MB — vendor PROOF sheets run 1-3 MB

# ext -> (content type, [accepted magic-byte prefixes])
ALLOWED = {
    ".jpg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".jpeg": ("image/jpeg", [b"\xff\xd8\xff"]),
    ".png": ("image/png", [b"\x89PNG\r\n\x1a\n"]),
    ".webp": ("image/webp", [b"RIFF"]),
    ".pdf": ("application/pdf", [b"%PDF-"]),
}
ACCEPT_ATTR = ".jpg,.jpeg,.png,.webp,.pdf"


def _load():
    if not INDEX.exists():
        return {}
    try:
        return json.loads(INDEX.read_text() or "{}")
    except (ValueError, OSError):
        return {}


def _save(d):
    DIR.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps(d, indent=2))


def _safe_id(event_id):
    """Slug an event id down to something that can never escape data/fliers/."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(event_id).strip()).strip("._-")


def _ext(filename):
    m = re.search(r"(\.[A-Za-z0-9]+)$", str(filename or "").strip())
    return (m.group(1).lower() if m else "")


def _is_real_class(event_id):
    """True when the id exists in the class catalog. Imported lazily so this
    module stays cheap for the read path (get_flier / flier_path)."""
    try:
        from src.catalog import load_catalog
        events, _, _ = load_catalog()
        return str(event_id) in events
    except Exception:  # noqa: BLE001 - catalog trouble shouldn't 500 an upload
        return True


def get_flier(event_id):
    """Metadata for one class. Always returns a dict; has_flier says the rest."""
    eid = str(event_id).strip()
    rec = _load().get(eid)
    if not rec or not (DIR / rec.get("file", "")).exists():
        return {"event_id": eid, "has_flier": False, "accept": ACCEPT_ATTR,
                "max_mb": MAX_BYTES // (1024 * 1024)}
    return {
        "event_id": eid,
        "has_flier": True,
        "url": f"/flier/{eid}",
        "original": rec.get("original", ""),
        "content_type": rec.get("content_type", ""),
        "is_pdf": rec.get("content_type") == "application/pdf",
        "size": rec.get("size", 0),
        "size_display": _human(rec.get("size", 0)),
        "uploaded_at": rec.get("uploaded_at", ""),
        "accept": ACCEPT_ATTR,
        "max_mb": MAX_BYTES // (1024 * 1024),
    }


def _human(n):
    n = int(n or 0)
    return f"{n / (1024 * 1024):.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"


def save_flier(event_id, filename, data_b64):
    """Decode, validate and store one flier. Replaces any existing one."""
    eid = str(event_id).strip()
    if not eid:
        return {"ok": False, "error": "Missing event_id."}
    safe = _safe_id(eid)
    if not safe:
        return {"ok": False, "error": "That class id can't be used for a file name."}
    if not _is_real_class(eid):
        # a flier only means something attached to a class in the catalog —
        # refusing unknown ids keeps data/fliers/ from collecting orphans
        return {"ok": False, "error": "That class isn't in the schedule."}

    ext = _ext(filename)
    if ext not in ALLOWED:
        return {"ok": False, "error": ("Use a JPG, PNG, WEBP or PDF flier — "
                                       f"'{filename}' isn't one of those.")}

    raw = str(data_b64 or "")
    if "," in raw[:64] and raw.lstrip().startswith("data:"):
        raw = raw.split(",", 1)[1]          # strip a data: URL prefix if present
    try:
        blob = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        return {"ok": False, "error": "That file didn't upload cleanly — try again."}

    if not blob:
        return {"ok": False, "error": "That file is empty."}
    if len(blob) > MAX_BYTES:
        return {"ok": False, "error": (f"That flier is {_human(len(blob))} — the limit is "
                                       f"{MAX_BYTES // (1024 * 1024)} MB. Save a smaller export.")}

    content_type, magics = ALLOWED[ext]
    if not any(blob.startswith(m) for m in magics):
        return {"ok": False, "error": (f"That file isn't really a {ext.lstrip('.').upper()} — "
                                       "re-export it and upload again.")}

    DIR.mkdir(parents=True, exist_ok=True)
    d = _load()
    old = (d.get(eid) or {}).get("file")
    if old and old != safe + ext:               # replacing jpg with pdf, etc.
        (DIR / old).unlink(missing_ok=True)

    target = DIR / (safe + ext)
    target.write_bytes(blob)
    d[eid] = {
        "file": safe + ext,
        "original": str(filename or "").strip(),
        "content_type": content_type,
        "size": len(blob),
        "uploaded_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }
    _save(d)
    return {"ok": True, "message": f"Custom flier uploaded ({_human(len(blob))}).",
            **get_flier(eid)}


def remove_flier(event_id):
    """Delete the flier for one class. The class page falls back to the
    generated banner — nothing else changes."""
    eid = str(event_id).strip()
    d = _load()
    rec = d.pop(eid, None)
    if not rec:
        return {"ok": False, "error": "This class has no custom flier."}
    (DIR / rec.get("file", "")).unlink(missing_ok=True)
    _save(d)
    return {"ok": True, "message": "Custom flier removed.", **get_flier(eid)}


def flier_path(event_id):
    """Absolute path of a class's flier, or None. Used by the public route —
    the name comes from the index, never from the URL, so /flier/<id> can't be
    walked out of data/fliers/."""
    rec = _load().get(str(event_id).strip())
    if not rec:
        return None, None
    p = DIR / rec.get("file", "")
    return (p, rec.get("content_type", "application/octet-stream")) if p.exists() else (None, None)
