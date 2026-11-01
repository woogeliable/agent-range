"""Adapter contract shared by all simulated platform endpoints."""
from abc import ABC, abstractmethod

class Adapter(ABC):
    name: str
    label: str
    prefix: str

    @abstractmethod
    def handle(self, handler, method: str, path: str, query: str, body: dict):
        """Return (status, headers, payload). Payload is a dict or raw bytes."""
        raise NotImplementedError
