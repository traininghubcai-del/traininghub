"""Load the simulated CSVs from data_global/ into typed records (stdlib csv).

Returns a small in-memory ``Dataset``. All file access goes through
chat_src.paths, so it can only ever read inside chat_bot/.
"""
import csv
from dataclasses import dataclass, field
from typing import List

from chat_src import config, paths
from chat_src.models import ClassRow, Dealer, Registration


@dataclass
class Dataset:
    classes: List[ClassRow] = field(default_factory=list)
    dealers: List[Dealer] = field(default_factory=list)
    registrations: List[Registration] = field(default_factory=list)

    def dealer_by_id(self, dealer_id):
        return next((d for d in self.dealers if d.dealer_id == dealer_id), None)


def _read_csv(filename):
    path = paths.get_data_global_path(filename)
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_dataset() -> Dataset:
    files = config.settings().get("data_files", {})
    return Dataset(
        classes=[ClassRow.from_row(r) for r in _read_csv(files.get("classes", "classes_sim.csv"))],
        dealers=[Dealer.from_row(r) for r in _read_csv(files.get("dealers", "dealers_sim.csv"))],
        registrations=[Registration.from_row(r)
                       for r in _read_csv(files.get("registrations", "registrations_sim.csv"))],
    )
