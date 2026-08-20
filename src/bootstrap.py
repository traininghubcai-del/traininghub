"""Seed a fresh data volume from the files baked into the image.

APP_DATA_DIR exists so the DB, the catalog and the email ledger can live on a
mounted volume and survive a redeploy. But a newly created volume is empty, and
DATA is where the app reads the class schedule from — so pointing APP_DATA_DIR
at a new volume without this would boot a site with no classes on it. The fix
that protects the registrations would be the outage.

So: on startup, any file the image ships in ./data that the volume doesn't have
yet gets copied in. Once.

Existing files are never touched. That is the whole safety property — after the
first boot the volume is the source of truth, and a deploy carrying a stale copy
of the catalog can't overwrite the edits John made through the Admin lens. It
also makes this safe to run on every boot, which is why it isn't guarded by a
marker file that could go missing.
"""
import shutil
from pathlib import Path

from config import DATA, HERE

# The catalog and the branch phone numbers are the only things the app needs in
# order to serve a page. Everything else (the DB, the outbox, fliers) is created
# on demand, and the PII files are deliberately not in the image at all.
BUNDLED = HERE / "data"


def seed_data_dir():
    """Copy bundled data files into DATA if they aren't there. Returns the names."""
    if not BUNDLED.is_dir() or BUNDLED.resolve() == DATA.resolve():
        return []                      # running on the bundled dir itself: nothing to do

    DATA.mkdir(parents=True, exist_ok=True)
    copied = []
    for src in sorted(BUNDLED.iterdir()):
        if src.name.startswith(".") or not src.is_file():
            continue
        dest = DATA / src.name
        if dest.exists():
            continue                   # the volume's copy wins, always
        try:
            shutil.copy2(src, dest)
            copied.append(src.name)
        except OSError as e:
            print(f"  warning: couldn't seed {src.name} ({e})")
    return copied
