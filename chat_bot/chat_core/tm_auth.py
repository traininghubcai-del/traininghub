"""Validate a TM access key against chat_config/tm_keys.yaml.

Returns the TM's identity + scope (branches, temp folder) on success, or None on
a bad key. No filesystem access beyond the sandboxed config read.
"""
from dataclasses import dataclass
from typing import List, Optional

from chat_src import config


@dataclass
class TMSession:
    tm_id: str
    display_name: str
    branches: List[str]
    temp_folder: str


def authenticate(key: str) -> Optional[TMSession]:
    key = (key or "").strip()
    if not key:
        return None
    for tm_id, cfg in config.tm_keys().get("tms", {}).items():
        if cfg.get("key") == key:
            return TMSession(
                tm_id=tm_id,
                display_name=cfg.get("display_name", tm_id),
                branches=list(cfg.get("branches", [])),
                temp_folder=cfg.get("temp_folder", ""),
            )
    return None
