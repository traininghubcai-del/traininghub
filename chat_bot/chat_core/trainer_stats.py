"""Compute a per-trainer snapshot: the classes they run, each class roster, and
attendance. Cached to data_temp/trainer_cache/trainer_<id>.json via chat_src.paths
(so strictly inside chat_bot/). Read by answer_trainer.
"""
import json
from datetime import datetime

from chat_rag.ingest import load_dataset
from chat_src import paths

_TODAY = datetime.now().date().isoformat()  # classes before today are past


def build_trainer_snapshot(session) -> dict:
    ds = load_dataset()
    # Match by explicit trainer_id when the catalog has one, else by the topics
    # this trainer covers (no real trainer→class schedule yet — Phase C).
    topics = set(session.topics)
    my_classes = [c for c in ds.classes
                  if c.trainer_id == session.trainer_id or c.topic in topics]
    dealer_name = {d.dealer_id: d.dealer_name for d in ds.dealers}

    classes_out = []
    total_registered = total_attended = 0
    for c in sorted(my_classes, key=lambda x: x.event_date):
        roster = []
        for r in ds.registrations:
            if r.event_id != c.event_id:
                continue
            roster.append({
                "dealer": dealer_name.get(r.dealer_id, r.dealer_id),
                "attendee_name": r.attendee_name,
                "role": r.role,
                "attended": r.attended,
                "status": r.status,
                "score": r.score,
            })
        attended = sum(1 for p in roster if p["attended"])
        total_registered += len(roster)
        total_attended += attended
        classes_out.append({
            "event_id": c.event_id, "topic": c.topic, "level": c.level,
            "branch": c.branch, "region": c.region, "event_date": c.event_date,
            "start_time": c.start_time, "end_time": c.end_time, "location": c.location,
            "capacity": c.capacity, "registered": len(roster), "attended": attended,
            "upcoming": c.event_date >= _TODAY, "roster": roster,
        })

    snapshot = {
        "trainer_id": session.trainer_id,
        "display_name": session.display_name,
        "topics": session.topics,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "totals": {
            "classes": len(classes_out),
            "upcoming": sum(1 for c in classes_out if c["upcoming"]),
            "registered": total_registered,
            "attended": total_attended,
        },
        "classes": classes_out,
    }
    paths.write_text(paths.get_trainer_cache_path(session.trainer_id),
                     json.dumps(snapshot, indent=2))
    return snapshot


def load_snapshot(trainer_id):
    path = paths.get_trainer_cache_path(trainer_id)
    if not path.exists():
        return None
    return json.loads(paths.read_text(path))
