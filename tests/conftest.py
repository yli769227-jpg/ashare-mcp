"""Shared pytest config. Keep deliberately minimal — tests are offline by design."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _block_real_akshare(monkeypatch):
    """Belt-and-braces safety net: if any test forgets to monkeypatch, blow up
    loud instead of silently hitting the real akshare network. Each module
    monkeypatches the *consumers* (peer_compare/history/http_app), so this only
    fires when something has been missed."""
    def _no_network(*args, **kwargs):
        raise RuntimeError(
            "real akshare call leaked into a test — fixture / monkeypatch missing"
        )

    import ashare_mcp.data_source as ds
    monkeypatch.setattr(ds, "_fetch_em", _no_network, raising=True)
