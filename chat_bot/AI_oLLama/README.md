# AI_oLLama — the Llama box

**The only module allowed to talk to a Llama runtime.** Everything else in
`chat_bot/` goes through the two public functions here, so we can swap the model
(local → cloud) without touching the rest of the app.

## Public API

```python
from AI_oLLama import ask_llama, system_prompt, is_available, LlamaUnavailable

ask_llama(messages)      # [{"role","content"}, ...] -> reply string
system_prompt("public")  # persona + safety text for a mode ("public" | "tm")
is_available()           # True if the local runtime answers (never raises)
```

`ask_llama` raises **`LlamaUnavailable`** when no runtime is reachable. The
router catches that and falls back to rule-based answers — so the chat works even
with no model installed.

## Files

- `llm_client.py` — HTTP client (stdlib only), config/prompt loading
- `model_config.yaml` — which model, temperature, base_url, limits
- `prompts.yaml` — system + safety prompts

## Running a local model (Ollama)

```sh
# 1. install Ollama (one-time)         https://ollama.com/download
brew install ollama            # macOS

# 2. start the server (leave running)
ollama serve

# 3. pull a lightweight model (one-time, ~2GB)
ollama pull llama3.2:3b        # or llama3.2:1b for the lightest

# 4. that's it — ask_llama() now uses it. Verify:
curl http://localhost:11434/api/tags
```

If Ollama isn't running, the assistant still answers (rule-based fallback).

## Moving to the cloud later

Replace the body of `ask_llama` in `llm_client.py` with a call to Claude / Groq /
OpenAI and set the key + model in `model_config.yaml`. Keep the signature
identical. Nothing else in `chat_bot/` changes.
