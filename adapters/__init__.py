"""Adapter registry: a new adapter module is imported and registered on one line."""
from .dify import DifyAdapter
from .coze import CozeAdapter
from .http import HttpAdapter

ADAPTERS = {}

def register(adapter_class):
    adapter = adapter_class()
    ADAPTERS[adapter.prefix.rstrip("/")] = adapter
    return adapter

register(CozeAdapter)
register(DifyAdapter)
register(HttpAdapter)
