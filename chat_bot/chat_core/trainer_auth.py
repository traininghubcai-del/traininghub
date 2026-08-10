"""Validate a trainer access code against chat_config/trainer_codes.yaml.

Returns the trainer's identity + the topics they teach on success, or None on a
bad code. No filesystem access beyond the sandboxed config read.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from chat_src import config


@dataclass
class TrainerSession:
    trainer_id: str
    display_name: str
    topics: List[str] = field(default_factory=list)


def authenticate(code: str) -> Optional[TrainerSession]:
    code = (code or "").strip()
    if not code:
        return None
    for trainer_id, cfg in config.trainer_codes().get("trainers", {}).items():
        if cfg.get("code") == code:
            return TrainerSession(
                trainer_id=trainer_id,
                display_name=cfg.get("display_name", trainer_id),
                topics=list(cfg.get("topics", [])),
            )
    return None
