"""AI_oLLama — the ONLY module that talks to a Llama runtime.

Public surface:
    ask_llama(messages) -> str       one chat completion (raises LlamaUnavailable)
    system_prompt(mode) -> str       persona/safety text from prompts.yaml
    is_available() -> bool           cheap ping of the local runtime

Everything Llama-specific (HTTP client, model choice, prompts) lives in this
folder. Swap the body of llm_client.ask_llama to move from local Ollama to a
hosted API later — no caller changes, because the signature is fixed.
"""
from AI_oLLama.llm_client import (  # noqa: F401
    LlamaUnavailable,
    ask_llama,
    is_available,
    system_prompt,
)
