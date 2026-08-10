"""Bridge between the landing-page server and the sandboxed chat_bot package.

The app only ever calls chat_core (per the architecture rules). We add chat_bot/
to sys.path once here, call chat_core.router.handle_message(), and return a small
dict for the front-end. handle_message returns a plain string (the contract);
we read the session afterward to tell the UI which mode it's in (for the badge).
All of chat_bot's file + Llama access stays inside chat_bot/.
"""
import sys
from pathlib import Path

_CHAT_BOT = Path(__file__).resolve().parent.parent / "chat_bot"
if str(_CHAT_BOT) not in sys.path:
    sys.path.insert(0, str(_CHAT_BOT))

from chat_core import state  # noqa: E402
from chat_core.router import handle_message  # noqa: E402


def handle_chat(session_id: str, message: str, mode: str = "",
                tm_key: str = "", trainer_code: str = "") -> dict:
    """One chat turn for the HTTP layer.

    Returns {reply, mode, tm_id, trainer_id, display_name} — display_name is the
    connected TM/trainer (for the header badge), empty in public mode.
    """
    session_id = (session_id or "anon").strip() or "anon"
    reply = handle_message(
        session_id=session_id,
        message=message,
        mode=(mode or None),
        tm_key=(tm_key or None),
        trainer_code=(trainer_code or None),
    )
    st = state.load(session_id)
    eff = st.get("last_mode", "public")
    display = (st.get("trainer_name") if eff == "trainer"
               else st.get("tm_name") if eff == "tm" else "")
    return {
        "reply": reply,
        "mode": eff,
        "tm_id": st.get("tm_id", ""),
        "trainer_id": st.get("trainer_id", ""),
        "display_name": display or "",
    }
