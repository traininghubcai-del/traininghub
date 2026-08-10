"""The one and only door to the filesystem for the whole chat_bot package.

Every read or write the chatbot performs MUST go through a path returned here.
Each resolver pins its result under ``chat_bot/`` (the package root) and raises
``SandboxError`` if a name tries to escape via ``..`` or an absolute path. That
single rule is what guarantees the spec's promise: *nothing in the chatbot ever
reads or writes outside chat_bot/.*

Layout (mirrors the spec):
    chat_bot/
      chat_config/      <- get_config_path()
      data_global/      <- get_data_global_path()   (read-only by convention)
      data_temp/
        sessions/       <- get_session_path(id)
        tm_cache/       <- get_tm_cache_path(tm_id)
      temp_1 .. temp_N/ <- get_temp_folder_path(name)
"""
from pathlib import Path

# chat_src/paths.py  ->  chat_src/  ->  chat_bot/
ROOT = Path(__file__).resolve().parent.parent


class SandboxError(Exception):
    """Raised when a requested path would fall outside chat_bot/."""


def _resolve(*parts: str) -> Path:
    """Join *parts under ROOT, resolve, and refuse anything that escapes ROOT."""
    candidate = ROOT.joinpath(*parts)
    resolved = candidate.resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise SandboxError(
            f"Refused path outside chat_bot sandbox: {'/'.join(parts)} -> {resolved}"
        ) from exc
    return resolved


# --- directory resolvers -----------------------------------------------------
def get_root() -> Path:
    return ROOT


def get_config_path(name: str = "") -> Path:
    return _resolve("chat_config", name) if name else _resolve("chat_config")


def get_data_global_path(name: str = "") -> Path:
    return _resolve("data_global", name) if name else _resolve("data_global")


def get_data_temp_path(name: str = "") -> Path:
    return _resolve("data_temp", name) if name else _resolve("data_temp")


def get_session_path(session_id: str) -> Path:
    safe = _slug(session_id)
    return _resolve("data_temp", "sessions", f"session_{safe}.json")


def get_tm_cache_path(tm_id: str) -> Path:
    safe = _slug(tm_id)
    return _resolve("data_temp", "tm_cache", f"tm_{safe}.json")


def get_trainer_cache_path(trainer_id: str) -> Path:
    safe = _slug(trainer_id)
    return _resolve("data_temp", "trainer_cache", f"trainer_{safe}.json")


def get_temp_folder_path(folder: str, name: str = "") -> Path:
    safe = _slug(folder)
    return _resolve(safe, name) if name else _resolve(safe)


def get_chat_rag_path(name: str = "") -> Path:
    return _resolve("chat_rag", name) if name else _resolve("chat_rag")


# --- safe I/O helpers (all routed through _resolve via the getters) -----------
def read_text(path: Path) -> str:
    return _checked(path).read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> Path:
    p = _checked(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def _checked(path: Path) -> Path:
    """Re-verify an already-resolved Path still lives under ROOT before I/O."""
    resolved = Path(path).resolve()
    try:
        resolved.relative_to(ROOT)
    except ValueError as exc:
        raise SandboxError(f"Refused I/O outside chat_bot sandbox: {resolved}") from exc
    return resolved


def _slug(value: str) -> str:
    """Reduce an arbitrary id to safe filename chars; blocks path traversal."""
    cleaned = "".join(c if (c.isalnum() or c in "-_") else "-" for c in str(value))
    return cleaned.strip("-") or "unknown"
