"""Build the RAG projections: index_classes.json + index_dealers.json.

These are lean, search-friendly views derived from data_global/. The chat reads
the indexes (not raw CSVs) so the retrieval surface is explicit and stable.

    python -m chat_rag.build_index
"""
import json

from chat_rag.ingest import load_dataset
from chat_src import paths


def build_class_index(ds):
    return [{
        "event_id": c.event_id,
        "topic": c.topic,
        "level": c.level,
        "region": c.region,
        "branch": c.branch,
        "event_date": c.event_date,
        "start_time": c.start_time,
        "end_time": c.end_time,
        "seats_remaining": c.seats_remaining,
        "capacity": c.capacity,
        "location": c.location,
        "trainer_id": c.trainer_id,
        "trainer_name": c.trainer_name,
        # one lowercased blob for cheap substring matching
        "search": " ".join([c.event_id, c.topic, c.level, c.region, c.branch,
                            c.event_date, c.trainer_name]).lower(),
    } for c in ds.classes]


def build_dealer_index(ds):
    by_dealer = {}
    for d in ds.dealers:
        by_dealer[d.dealer_id] = {
            "dealer_id": d.dealer_id, "dealer_name": d.dealer_name,
            "branch": d.branch, "tm_id": d.tm_id, "tier": d.tier,
            "enrollments": 0, "attended": 0, "completed": 0,
        }
    for r in ds.registrations:
        b = by_dealer.get(r.dealer_id)
        if not b:
            continue
        b["enrollments"] += 1
        b["attended"] += 1 if r.attended else 0
        b["completed"] += 1 if r.status == "Completed" else 0
    return list(by_dealer.values())


def build(dataset=None):
    ds = dataset or load_dataset()
    classes = build_class_index(ds)
    dealers = build_dealer_index(ds)
    _write("index_classes.json", classes)
    _write("index_dealers.json", dealers)
    return classes, dealers


def load_class_index():
    return _read("index_classes.json")


def load_dealer_index():
    return _read("index_dealers.json")


def _write(name, obj):
    path = paths.get_chat_rag_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def _read(name):
    path = paths.get_chat_rag_path(name)
    if not path.exists():       # build on first use if missing
        build()
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    classes, dealers = build()
    print(f"index_classes.json: {len(classes)} rows")
    print(f"index_dealers.json: {len(dealers)} rows")


if __name__ == "__main__":
    main()
