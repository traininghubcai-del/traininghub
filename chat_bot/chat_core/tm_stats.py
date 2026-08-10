"""Compute a per-TM stats snapshot from the simulated data and cache it.

build_tm_snapshot(session):
  1. load global sim data
  2. filter to the TM's branches
  3. aggregate per-dealer training history + a 'behind on Level 1' list
  4. write data_temp/tm_cache/tm_<id>.json (canonical, read by answer_tm) and a
     human-readable per-dealer CSV into the TM's temp_N/ folder (demo artifact).

Everything writes through chat_src.paths, so strictly inside chat_bot/.
"""
import csv
import json
from datetime import datetime

from chat_rag.ingest import load_dataset
from chat_src import config, paths


def _passing():
    return config.rag_config().get("thresholds", {}).get("passing_score", 70)


def _level1_topic():
    return config.rag_config().get("thresholds", {}).get("level1_topic",
                                                          "FIT INSTALL & COMMISSIONING")


def build_tm_snapshot(session) -> dict:
    ds = load_dataset()
    branches = set(session.branches)

    dealers = [d for d in ds.dealers if d.branch in branches]
    regs = [r for r in ds.registrations if r.branch in branches]
    # TMs are people-scoped, not branch-scoped (a dealer's `branch` carries its
    # TM's name) — and any TM can send dealers to any class, so keep them all.
    classes = list(ds.classes)
    level1 = _level1_topic()
    passing = _passing()

    per_dealer = {}
    for d in dealers:
        per_dealer[d.dealer_id] = {
            "dealer_id": d.dealer_id, "dealer_name": d.dealer_name, "branch": d.branch,
            "tier": d.tier, "primary_contact": d.primary_contact,
            "contact_email": d.contact_email, "enrollments": 0, "attended": 0,
            "completed": 0, "no_shows": 0, "avg_score": 0.0,
            "level1_passed": False, "history": [],
        }

    score_acc = {}
    for r in regs:
        bucket = per_dealer.get(r.dealer_id)
        if bucket is None:
            continue
        bucket["enrollments"] += 1
        if r.attended:
            bucket["attended"] += 1
        if r.status == "Completed":
            bucket["completed"] += 1
        if r.status == "No Show":
            bucket["no_shows"] += 1
        if r.attended and r.score:
            score_acc.setdefault(r.dealer_id, []).append(r.score)
        if _topic_of(classes, r.event_id) == level1 and r.attended and r.score >= passing:
            bucket["level1_passed"] = True
        bucket["history"].append({
            "event_id": r.event_id, "topic": _topic_of(classes, r.event_id),
            "level": r.level, "attended": r.attended, "score": r.score,
            "status": r.status, "date": r.reg_date,
        })

    for did, scores in score_acc.items():
        per_dealer[did]["avg_score"] = round(sum(scores) / len(scores), 1)

    behind_level1 = [
        {"dealer_id": b["dealer_id"], "dealer_name": b["dealer_name"], "branch": b["branch"]}
        for b in per_dealer.values() if not b["level1_passed"]
    ]

    snapshot = {
        "tm_id": session.tm_id, "display_name": session.display_name,
        "branches": session.branches,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "totals": {
            "dealers": len(dealers), "classes": len(classes),
            "enrollments": len(regs), "behind_on_level1": len(behind_level1),
        },
        "dealers": list(per_dealer.values()),
        "behind_on_level1": behind_level1,
    }
    _write_cache(session, snapshot)
    return snapshot


def _topic_of(classes, event_id):
    return next((c.topic for c in classes if c.event_id == event_id), "")


def _write_cache(session, snapshot):
    paths.write_text(paths.get_tm_cache_path(session.tm_id), json.dumps(snapshot, indent=2))
    if session.temp_folder:
        rows = [{
            "dealer_name": d["dealer_name"], "branch": d["branch"], "tier": d["tier"],
            "enrollments": d["enrollments"], "attended": d["attended"],
            "completed": d["completed"], "no_shows": d["no_shows"],
            "avg_score": d["avg_score"], "level1_passed": d["level1_passed"],
        } for d in snapshot["dealers"]]
        if rows:
            csv_path = paths.get_temp_folder_path(session.temp_folder, "dealers_summary.csv")
            csv_path.parent.mkdir(parents=True, exist_ok=True)
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)


def load_snapshot(tm_id):
    path = paths.get_tm_cache_path(tm_id)
    if not path.exists():
        return None
    return json.loads(paths.read_text(path))
