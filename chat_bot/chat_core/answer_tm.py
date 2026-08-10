"""TM-mode answering, driven by the cached snapshot (tm_cache/tm_<id>.json).

Like answer_public, returns (context, fallback): an LLM context block plus a
rule-based reply. Picks the relevant slice (dealer roster vs. behind-on-Level-1)
from the question. Never calls Llama itself.
"""
from chat_core.tm_stats import load_snapshot


def _intent(message):
    low = message.lower()
    if any(k in low for k in ("behind", "level 1", "level1", "laggard", "lagging")):
        return "behind"
    return "roster"


def _dealer_line(d):
    tail = "" if d["level1_passed"] else "  [Level 1 NOT passed]"
    return (f"{d['dealer_name']} ({d['branch']}, {d['tier']}): {d['enrollments']} enrolled / "
            f"{d['attended']} attended / {d['completed']} completed, avg {d['avg_score']}{tail}")


def gather(tm_id, message):
    snap = load_snapshot(tm_id)
    if snap is None:
        return ("No snapshot available.",
                "I couldn't load your territory data. Try signing in again with your key.")

    intent = _intent(message)
    name = snap["display_name"]

    if intent == "behind":
        behind = snap["behind_on_level1"]
        context = (f"Territory: {name}. Dealers behind on Level 1 ({len(behind)}):\n"
                   + ("\n".join(f"- {d['dealer_name']} ({d['branch']})" for d in behind) or "- none"))
        if not behind:
            fallback = f"Good news — every dealer in {name} has passed Level 1."
        else:
            lines = "\n".join(f"  • {d['dealer_name']} ({d['branch']})" for d in behind)
            fallback = f"{len(behind)} dealer(s) behind on Level 1 in {name}:\n{lines}"
        return context, fallback

    # roster + history
    context = (f"Territory: {name} ({snap['totals']['dealers']} dealers).\n"
               + "\n".join(f"- {_dealer_line(d)}" for d in snap["dealers"]))
    lines = "\n".join(f"  • {_dealer_line(d)}" for d in snap["dealers"])
    fallback = f"{name} — {snap['totals']['dealers']} dealers:\n{lines}"
    return context, fallback
