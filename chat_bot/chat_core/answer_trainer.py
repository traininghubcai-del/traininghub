"""Trainer-mode answering, driven by the cached snapshot
(trainer_cache/trainer_<id>.json). Returns (context, fallback): an LLM context
block plus a rule-based reply. Never calls Llama itself.
"""
from chat_core.trainer_stats import load_snapshot


def _intent(message):
    low = message.lower()
    if any(k in low for k in ("upcoming", "next", "schedule", "coming up")):
        return "upcoming"
    if any(k in low for k in ("roster", "who", "attend", "missing", "no show", "no-show", "signed up")):
        return "roster"
    return "overview"


def _class_brief(c):
    when = "upcoming" if c["upcoming"] else "past"
    return (f"{c['topic']} ({c['level']}) at {c['region']}, {c['event_date']} "
            f"[{when}] — {c['registered']} registered, {c['attended']} attended")


def gather(trainer_id, message):
    snap = load_snapshot(trainer_id)
    if snap is None:
        return ("No snapshot available.",
                "I couldn't load your trainer data. Try entering your code again.")

    name = snap["display_name"]
    intent = _intent(message)
    classes = snap["classes"]

    if intent == "upcoming":
        up = [c for c in classes if c["upcoming"]]
        context = (f"Trainer: {name}. Upcoming classes ({len(up)}):\n"
                   + ("\n".join(f"- {_class_brief(c)}" for c in up) or "- none"))
        if not up:
            fallback = f"You have no upcoming classes scheduled, {name.split()[0]}."
        else:
            lines = "\n".join(f"  • {_class_brief(c)}" for c in up)
            fallback = f"Your upcoming classes:\n{lines}"
        return context, fallback

    if intent == "roster":
        # include rosters so the LLM can answer "who attended / who's missing"
        blocks = []
        for c in classes:
            people = "\n".join(
                f"    * {p['attendee_name']} ({p['dealer']}, {p['role']}) — "
                f"{'attended' if p['attended'] else 'NOT attended'}, {p['status']}"
                for p in c["roster"]) or "    * (no registrations)"
            blocks.append(f"- {c['topic']} @ {c['region']} {c['event_date']}:\n{people}")
        context = f"Trainer: {name}. Class rosters:\n" + "\n".join(blocks)
        # rule-based fallback: compact per-class attendance counts
        lines = "\n".join(f"  • {_class_brief(c)}" for c in classes)
        fallback = f"{name} — class rosters & attendance:\n{lines}"
        return context, fallback

    # overview
    t = snap["totals"]
    context = (f"Trainer: {name}. Totals: {t['classes']} classes "
               f"({t['upcoming']} upcoming), {t['registered']} registered, "
               f"{t['attended']} attended.\n"
               + "\n".join(f"- {_class_brief(c)}" for c in classes))
    lines = "\n".join(f"  • {_class_brief(c)}" for c in classes)
    fallback = (f"{name} — {t['classes']} classes, {t['upcoming']} upcoming, "
                f"{t['attended']}/{t['registered']} attended:\n{lines}")
    return context, fallback
