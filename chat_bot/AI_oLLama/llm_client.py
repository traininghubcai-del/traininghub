"""The single bridge to a Llama runtime. Stdlib HTTP only (no extra deps).

Today this calls a local Ollama server (http://localhost:11434/api/chat).
To move to the cloud later, replace the body of ``ask_llama`` with a call to
Claude / Groq / OpenAI — keep the signature identical and nothing else changes.

Config (model, temperature, base_url) is read from model_config.yaml in this
same folder; prompts from prompts.yaml. Both are resolved relative to THIS file
so AI_oLLama stays self-contained and never imports chat_core/chat_rag.
"""
import json
import urllib.error
import urllib.request
from pathlib import Path

import yaml

_HERE = Path(__file__).resolve().parent
_cfg_cache: dict = {}
_prompt_cache: dict = {}


class LlamaUnavailable(Exception):
    """Raised when the Llama runtime can't be reached or errors out.

    Callers (the router) catch this and fall back to rule-based answers, so the
    chat keeps working even with no model installed.
    """


def _config() -> dict:
    if not _cfg_cache:
        _cfg_cache.update(yaml.safe_load((_HERE / "model_config.yaml").read_text()) or {})
    return _cfg_cache


def _prompts() -> dict:
    if not _prompt_cache:
        _prompt_cache.update(yaml.safe_load((_HERE / "prompts.yaml").read_text()) or {})
    return _prompt_cache


def system_prompt(mode: str) -> str:
    """Persona + safety text for 'public', 'tm', or 'trainer' mode."""
    p = _prompts()
    key = {"tm": "system_tm", "trainer": "system_trainer"}.get(mode, "system_public")
    base = p.get(key, p.get("system_public", ""))
    return f"{base.strip()}\n\n{p.get('safety', '').strip()}"


def is_available() -> bool:
    """Cheap check: is the Ollama server up? Never raises."""
    cfg = _config()
    url = f"{cfg.get('base_url', 'http://localhost:11434')}/api/tags"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


def ask_llama(messages: list[dict]) -> str:
    """One chat completion. messages = [{"role","content"}, ...] -> reply string.

    Raises LlamaUnavailable if the runtime is unreachable, times out, or errors.
    """
    cfg = _config()
    base = cfg.get("base_url", "http://localhost:11434")
    payload = {
        "model": cfg.get("model", "llama3.2:3b"),
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": cfg.get("temperature", 0.3),
            "num_predict": cfg.get("max_tokens", 400),
        },
    }
    req = urllib.request.Request(
        f"{base}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=cfg.get("timeout_seconds", 30)) as resp:
            data = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise LlamaUnavailable(f"Llama runtime not reachable at {base}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001
        raise LlamaUnavailable(f"Llama call failed: {exc}") from exc

    reply = (data.get("message") or {}).get("content", "").strip()
    if not reply:
        raise LlamaUnavailable("Llama returned an empty reply.")
    return reply
