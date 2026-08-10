"""Load the three YAML config files, always via chat_src.paths (sandboxed).

settings.yaml   - global toggles (base_url, demo flags)
tm_keys.yaml    - access key -> TM id / branches / temp folder
rag_config.yaml - which columns the public RAG may expose, thresholds
"""
import yaml

from chat_src import paths

_cache: dict = {}


def _load(name: str) -> dict:
    if name not in _cache:
        text = paths.read_text(paths.get_config_path(name))
        _cache[name] = yaml.safe_load(text) or {}
    return _cache[name]


def settings() -> dict:
    return _load("settings.yaml")


def tm_keys() -> dict:
    return _load("tm_keys.yaml")


def trainer_codes() -> dict:
    return _load("trainer_codes.yaml")


def rag_config() -> dict:
    return _load("rag_config.yaml")


def reload() -> None:
    """Drop the cache so edited YAML is picked up (handy in the demo)."""
    _cache.clear()
