"""Registrations -> .xlsx in John's exact column order, plus the live mirror file.

The mirror (data/registrations.xlsx) is rewritten after every submit so John can
just open it. Writes are lock-guarded + atomic so a concurrent submit can't leave
a half-written file.
"""
import io
import os
import threading

from openpyxl import Workbook

from config import COLUMNS, REG_XLSX

_XLSX_LOCK = threading.Lock()


def registrations_xlsx_bytes(repo):
    wb = Workbook()
    ws = wb.active
    ws.title = "registrations"
    ws.append([header for header, _ in COLUMNS])
    for r in repo.all_registrations_flat():
        ws.append([r.get(col, "") for _, col in COLUMNS])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def write_registrations_xlsx(repo):
    """Rewrite data/registrations.xlsx from the DB (lock-guarded + atomic)."""
    with _XLSX_LOCK:
        data = registrations_xlsx_bytes(repo)
        tmp = REG_XLSX.with_name(REG_XLSX.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, REG_XLSX)  # atomic swap — readers never see a half file
