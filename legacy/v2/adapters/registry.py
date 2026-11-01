"""Convenience export for the one-line adapter registration contract."""
from . import ADAPTERS

def get_adapter(prefix):
    return ADAPTERS.get(prefix)
