"""Database layer. All SQL lives behind the repository interface here.

`get_repository()` returns the backend selected by config.DB_BACKEND, so app code
never imports a specific driver. To migrate off SQLite, add a sibling module
(e.g. postgres_repo.py) implementing Repository and register it below.
"""
from config import DB_BACKEND


def get_repository():
    if DB_BACKEND == "sqlite":
        from src.db.sqlite_repo import SqliteRepository
        return SqliteRepository()
    raise ValueError(f"Unknown DB_BACKEND: {DB_BACKEND!r}")
