"""chat_core — the brains. The ONLY package the rest of the app calls.

Public entrypoint:
    router.handle_message(session_id, message, tm_key) -> str

It authenticates TMs, gathers context from chat_rag/ + data_temp/, optionally
calls AI_oLLama.ask_llama(), and returns the final reply text. No other package
outside chat_bot/ should import anything but this.

Re-exported here so callers never reach into AI_oLLama directly:
    llm_available() -> bool   (is a local Llama runtime up?)
"""
from AI_oLLama import is_available as llm_available  # noqa: F401
