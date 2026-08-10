"""Table-driven retrieval over index_classes.json. No vectors — for the demo,
retrieval is filtering by branch / topic / open seats, plus a tiny keyword parser
that pulls branch codes and topic aliases out of a free-text question.
"""
import re

from chat_rag.build_index import load_class_index
from chat_src import config

_REGIONS = ("nashville", "murfreesboro", "columbia", "cookeville",
            "knoxville", "clarksville")


def parse_query(text):
    low = text.lower()
    hints = {"branch": None, "topic": None, "open_only": False}

    m = re.search(r"\b(\d{3})\b", low)
    if m:
        hints["branch"] = m.group(1)
    else:
        for region in _REGIONS:
            if region in low:
                hints["branch"] = region
                break

    for alias, canonical in config.rag_config().get("topic_aliases", {}).items():
        if alias in low:
            hints["topic"] = canonical
            break

    if any(w in low for w in ("open", "available", "seats", "slots", "spots", "left")):
        hints["open_only"] = True
    return hints


def retrieve(text, index=None):
    """Return (matching class dicts, hints). Empty hints -> return all classes."""
    rows = index or load_class_index()
    hints = parse_query(text)
    out = rows
    if hints["branch"]:
        out = [c for c in out if hints["branch"] in c["branch"].lower()]
    if hints["topic"]:
        out = [c for c in out if c["topic"] == hints["topic"]]
    if hints["open_only"]:
        out = [c for c in out if c["seats_remaining"] > 0]
    out = sorted(out, key=lambda c: c["event_date"])
    return out, hints
