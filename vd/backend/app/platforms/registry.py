from .base import Adapter
from .youtube import YouTube

_ADAPTERS: dict[str, Adapter] = {}


def register(a: Adapter) -> None:
    _ADAPTERS[a.id] = a


def get(pid: str) -> Adapter:
    if pid not in _ADAPTERS:
        raise KeyError(pid)
    return _ADAPTERS[pid]


def enabled() -> list[dict]:
    return [{"id": a.id, "name": a.name} for a in _ADAPTERS.values()]


register(YouTube())  # add new platforms here
