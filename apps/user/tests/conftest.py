"""Shared fixtures for apps.user tests."""

from __future__ import annotations

import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def _clear_cache():
    """Locmem cache persists across tests in a process; start each one clean."""
    cache.clear()
    yield
    cache.clear()
