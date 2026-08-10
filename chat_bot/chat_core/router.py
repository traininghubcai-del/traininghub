"""The one public entrypoint for the whole chat. Decides public / TM / Trainer
mode, gathers the right context (chat_rag for public, the cached snapshot for TM
and Trainer), builds the message list, and asks the LLM — falling back to
rule-based answers when no Llama runtime is available.

    handle_message(session_id, message, mode=None, tm_key=None, trainer_code=None) -> str

`mode` is the lens the UI toggle requested ("public" | "tm" | "trainer"). The
session remembers any authenticated tm_id / trainer_id, so follow-up questions
don't need the key again. If `mode` is omitted we infer it from what's been
authenticated (trainer > tm > public) for backward compatibility.
"""
from AI_oLLama import LlamaUnavailable, ask_llama, system_prompt
from chat_core import (answer_public, answer_tm, answer_trainer, state,
                       tm_auth, tm_stats, trainer_auth, trainer_stats)


def _build_messages(mode, context, history, message):
    """system (persona+safety) + injected CONTEXT, then prior turns, then the ask."""
    system = system_prompt(mode)
    msgs = [{"role": "system", "content": f"{system}\n\nCONTEXT:\n{context}"}]
    msgs.extend(history)
    msgs.append({"role": "user", "content": message})
    return msgs


def _effective_mode(requested, st):
    """Resolve the lens to actually use, honoring auth state."""
    if requested == "tm":
        return "tm" if st.get("tm_id") else "public"
    if requested == "trainer":
        return "trainer" if st.get("trainer_id") else "public"
    if requested == "public":
        return "public"
    # no explicit request -> infer from what's authenticated
    if st.get("trainer_id"):
        return "trainer"
    if st.get("tm_id"):
        return "tm"
    return "public"


def handle_message(session_id, message, mode=None, tm_key=None, trainer_code=None):
    message = (message or "").strip()
    st = state.load(session_id)
    prelude = ""

    # 1) authenticate if a key/code was submitted this turn
    if tm_key:
        sess = tm_auth.authenticate(tm_key)
        if sess is None:
            prelude = "That TM access key wasn't recognized. "
        else:
            tm_stats.build_tm_snapshot(sess)
            st["tm_id"] = sess.tm_id
            st["tm_name"] = sess.display_name
            mode = "tm"
            prelude = f"✅ Connected as Territory Manager · {sess.display_name}. "
            if not message:
                message = "Give me a quick overview of my dealers."

    if trainer_code:
        tsess = trainer_auth.authenticate(trainer_code)
        if tsess is None:
            prelude = "That trainer code wasn't recognized. "
        else:
            trainer_stats.build_trainer_snapshot(tsess)
            st["trainer_id"] = tsess.trainer_id
            st["trainer_name"] = tsess.display_name
            mode = "trainer"
            prelude = f"✅ Connected as Trainer · {tsess.display_name}. "
            if not message:
                message = "Give me an overview of my classes and attendance."

    # 2) resolve which lens to answer in
    eff = _effective_mode(mode, st)

    # asked for a privileged mode but not authenticated -> nudge, answer public
    if mode == "tm" and eff != "tm" and not tm_key:
        prelude = prelude or "Enter your TM access key to see your territory. "
    if mode == "trainer" and eff != "trainer" and not trainer_code:
        prelude = prelude or "Enter your trainer code to see your classes. "

    # 3) build context for the resolved mode
    if eff == "tm":
        context, fallback = answer_tm.gather(st["tm_id"], message)
    elif eff == "trainer":
        context, fallback = answer_trainer.gather(st["trainer_id"], message)
    else:
        context, fallback = answer_public.gather(message)

    # 4) try the LLM; fall back to rule-based text if unavailable
    try:
        messages = _build_messages(eff, context, st.get("history", []), message)
        reply = ask_llama(messages)
    except LlamaUnavailable:
        reply = fallback

    reply = (prelude + reply).strip()

    # 5) persist short-term memory + remember which lens we answered in
    st["last_mode"] = eff
    state.append_turn(st, "user", message)
    state.append_turn(st, "assistant", reply)
    state.save(st)
    return reply
