"""Tiny per-session store: remembers a session's mode (public/TM) and history.

Persisted as data_temp/sessions/session_<id>.json via chat_src.paths so it stays
inside the sandbox. Keeps the last N turns so the LLM has short-term memory.
"""
import json

from chat_src import paths

_MAX_TURNS = 12  # keep last N messages (user+assistant) in history


def load(session_id):
    path = paths.get_session_path(session_id)
    if path.exists():
        try:
            return json.loads(paths.read_text(path))
        except (ValueError, OSError):
            pass
    return {"session_id": session_id, "tm_id": "", "tm_name": "",
            "trainer_id": "", "trainer_name": "", "last_mode": "public",
            "history": []}


def save(state):
    state["history"] = state.get("history", [])[-_MAX_TURNS:]
    paths.write_text(paths.get_session_path(state["session_id"]), json.dumps(state, indent=2))


def append_turn(state, role, content):
    state.setdefault("history", []).append({"role": role, "content": content})
