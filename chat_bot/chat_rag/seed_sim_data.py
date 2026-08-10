"""Dev tool: (re)generate the simulated CSVs under data_global/, then rebuild the
RAG indexes. Deterministic (fixed seed) so demo data is stable. Writes only
inside chat_bot/ via chat_src.paths. Run:

    python -m chat_rag.seed_sim_data
"""
import csv
import random

from chat_src import paths

SEED = 42

# Branch -> (region, tm_id). Mirrors real branch codes; tm_id mirrors tm_keys.yaml.
BRANCHES = {
    "101- Nashville":    ("Nashville", "tm_nashville"),
    "107- Murfreesboro": ("Murfreesboro", "tm_nashville"),
    "125- Columbia":     ("Columbia", "tm_columbia"),
    "132- Cookeville":   ("Cookeville", "tm_columbia"),
    "160- Knoxville":    ("Knoxville", "tm_knoxville"),
    "145- Clarksville":  ("Clarksville", "tm_knoxville"),
}

# topic -> (level, default capacity). Level 1 == FIT (see rag_config level1_topic).
TOPICS = {
    "FIT INSTALL & COMMISSIONING":        ("Level 1", 24),
    "MINI SPLIT INSTALL":                 ("Level 2", 20),
    "DUCTLESS SERVICE & TROUBLESHOOTING": ("Level 2", 16),
    "AIRFLOW & BALANCING":                ("Level 3", 18),
    "HEAT PUMP SERVICE":                  ("Level 3", 16),
}

# topic -> (trainer_id, trainer_name). Mirrors chat_config/trainer_codes.yaml.
TRAINERS = {
    "FIT INSTALL & COMMISSIONING":        ("trainer_micah", "Micah Sandlin"),
    "MINI SPLIT INSTALL":                 ("trainer_micah", "Micah Sandlin"),
    "AIRFLOW & BALANCING":                ("trainer_craig", "Craig Jones"),
    "DUCTLESS SERVICE & TROUBLESHOOTING": ("trainer_craig", "Craig Jones"),
    "HEAT PUMP SERVICE":                  ("trainer_dana", "Dana Reed"),
}

CLASSES = [
    ("nashville-fit-2026-04-29",        "101- Nashville",    "FIT INSTALL & COMMISSIONING",        "2026-04-29", "09:00", "15:00"),
    ("nashville-fit-2026-06-03",        "101- Nashville",    "FIT INSTALL & COMMISSIONING",        "2026-06-03", "09:00", "15:00"),
    ("nashville-mini-split-2026-06-10", "101- Nashville",    "MINI SPLIT INSTALL",                 "2026-06-10", "09:00", "15:00"),
    ("murfreesboro-airflow-2026-06-05", "107- Murfreesboro", "AIRFLOW & BALANCING",                "2026-06-05", "09:00", "12:00"),
    ("murfreesboro-heatpump-2026-06-19","107- Murfreesboro", "HEAT PUMP SERVICE",                  "2026-06-19", "09:00", "12:00"),
    ("murfreesboro-ductless-2026-07-15","107- Murfreesboro", "DUCTLESS SERVICE & TROUBLESHOOTING", "2026-07-15", "09:00", "12:00"),
    ("columbia-mini-split-2026-06-04",  "125- Columbia",     "MINI SPLIT INSTALL",                 "2026-06-04", "09:00", "15:00"),
    ("columbia-fit-2026-06-17",         "125- Columbia",     "FIT INSTALL & COMMISSIONING",        "2026-06-17", "09:00", "15:00"),
    ("columbia-airflow-2026-06-18",     "125- Columbia",     "AIRFLOW & BALANCING",                "2026-06-18", "09:00", "12:00"),
    ("cookeville-heatpump-2026-06-09",  "132- Cookeville",   "HEAT PUMP SERVICE",                  "2026-06-09", "09:00", "12:00"),
    ("cookeville-fit-2026-06-23",       "132- Cookeville",   "FIT INSTALL & COMMISSIONING",        "2026-06-23", "09:00", "15:00"),
    ("knoxville-mini-split-2026-06-11", "160- Knoxville",    "MINI SPLIT INSTALL",                 "2026-06-11", "09:00", "15:00"),
    ("knoxville-airflow-2026-06-25",    "160- Knoxville",    "AIRFLOW & BALANCING",                "2026-06-25", "09:00", "12:00"),
]

DEALER_NAMES = [
    "Volunteer Comfort Co", "Music City HVAC", "Cumberland Air Systems",
    "Rocky Top Heating & Air", "Stones River Mechanical", "Duck River Climate",
    "Highland Rim HVAC", "Caney Fork Comfort", "Smoky Mountain Air",
    "Clinch Valley Mechanical", "Red River Heating", "Fort Campbell Climate",
]
TIERS = ["Bronze", "Silver", "Gold"]
ROLES = ["Technician", "Inside Sales", "Outside Sales", "Owner"]
FIRST = ["Jake", "Maria", "Tyler", "Dana", "Chris", "Sam", "Pat", "Alex", "Jordan", "Casey", "Drew", "Robin"]
LAST = ["Hayes", "Nguyen", "Carter", "Lopez", "Reed", "Boone", "Frye", "Tate", "Marsh", "Pope", "Vance", "Dill"]


def _people(rng, n):
    return [f"{rng.choice(FIRST)} {rng.choice(LAST)}" for _ in range(n)]


def generate():
    rng = random.Random(SEED)

    dealers = []
    name_pool = list(DEALER_NAMES)
    rng.shuffle(name_pool)
    di = 0
    for branch, (region, tm_id) in BRANCHES.items():
        for _ in range(2):
            name = name_pool[di % len(name_pool)]
            di += 1
            contact = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
            slug = name.lower().replace(" ", "").replace("&", "")[:12]
            dealers.append({
                "dealer_id": f"d{di:03d}", "dealer_name": name, "branch": branch,
                "tm_id": tm_id, "tier": rng.choice(TIERS), "primary_contact": contact,
                "contact_email": f"{contact.split()[0].lower()}@{slug}.com",
            })

    dealers_by_branch = {}
    for d in dealers:
        dealers_by_branch.setdefault(d["branch"], []).append(d)

    classes, regs = [], []
    rid = 0
    for event_id, branch, topic, date, start, end in CLASSES:
        region, tm_id = BRANCHES[branch]
        level, cap = TOPICS[topic]
        roster = dealers_by_branch[branch]
        enrolled = rng.sample(roster, k=rng.randint(1, len(roster)))
        taken = 0
        for dealer in enrolled:
            for who in _people(rng, rng.randint(1, 3)):
                rid += 1
                taken += 1
                past = date < "2026-05-31"
                attended = past and rng.random() > 0.12
                if not past:
                    status, score, attended = "In Progress", 0, False
                elif not attended:
                    status, score = "No Show", 0
                else:
                    score = rng.randint(55, 99)
                    status = "Completed" if score >= 70 else "In Progress"
                regs.append({
                    "reg_id": f"r{rid:04d}", "event_id": event_id, "dealer_id": dealer["dealer_id"],
                    "attendee_name": who, "role": rng.choice(ROLES), "branch": branch,
                    "tm_id": tm_id, "level": level, "attended": "yes" if attended else "no",
                    "score": score, "status": status, "reg_date": date,
                })
        trainer_id, trainer_name = TRAINERS[topic]
        classes.append({
            "event_id": event_id, "region": region, "branch": branch, "tm_id": tm_id,
            "topic": topic, "level": level, "event_date": date, "start_time": start,
            "end_time": end, "capacity": cap, "seats_taken": taken,
            "seats_remaining": max(cap - taken, 0), "location": f"{region.upper()} BRANCH",
            "trainer_id": trainer_id, "trainer_name": trainer_name,
        })
    return classes, dealers, regs


def _write(filename, rows, fieldnames):
    path = paths.get_data_global_path(filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    return path, len(rows)


def main():
    classes, dealers, regs = generate()
    for path, n in [
        _write("classes_sim.csv", classes, list(classes[0].keys())),
        _write("dealers_sim.csv", dealers, list(dealers[0].keys())),
        _write("registrations_sim.csv", regs, list(regs[0].keys())),
    ]:
        print(f"wrote {n:3d} rows -> {path.relative_to(paths.get_root().parent)}")

    # rebuild indexes so retrieval matches the fresh data
    from chat_rag.build_index import main as build_main
    build_main()


if __name__ == "__main__":
    main()
