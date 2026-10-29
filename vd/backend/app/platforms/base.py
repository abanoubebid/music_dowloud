from abc import ABC, abstractmethod


class Adapter(ABC):
    """Contract every platform adapter implements."""
    id: str
    name: str

    @abstractmethod
    def validate(self, url: str) -> str: ...  # clean URL or ValueError

    @abstractmethod
    def analyze(self, url: str, scope: str, max_items: int) -> dict: ...

    @abstractmethod
    def entry_url(self, entry_id: str) -> str: ...

    @abstractmethod
    def stream_plan(self, kind: str, quality: str, containers: dict) -> dict: ...
