"""Public-mode answering. Retrieves matching classes from chat_rag and produces:

  - context: a compact text block fed to the LLM as ground truth
  - fallback: a ready-to-send rule-based reply for when no LLM is available

The router decides which to send. answer_public never calls Llama itself.
"""
from chat_rag import retrieve


def _class_line(c):
    seats = f"{c['seats_remaining']} of {c['capacity']} seats open" if c["seats_remaining"] else "FULL"
    return (f"{c['region']} — {c['topic']} ({c['level']}), {c['event_date']} "
            f"{c['start_time']}-{c['end_time']}, {seats}, at {c['location']}")


def gather(message):
    matches, hints = retrieve.retrieve(message)

    if not matches:
        context = "No classes match the question."
    else:
        context = "Available classes:\n" + "\n".join(f"- {_class_line(c)}" for c in matches)

    # rule-based fallback reply (used when Llama is offline)
    if not matches:
        fallback = ("I couldn't find classes matching that. Try a branch (Nashville, "
                    "Columbia, Knoxville…) or a topic (FIT, Mini Split, Airflow, Heat Pump).")
    else:
        lead = "Here are the classes I found"
        if hints["topic"]:
            lead = f"{hints['topic'].title()} classes"
        if hints["branch"]:
            lead += f" in {str(hints['branch']).title()}"
        lines = "\n".join(f"  • {_class_line(c)}" for c in matches[:8])
        fallback = f"{lead}:\n{lines}"

    return context, fallback
