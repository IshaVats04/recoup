"""RazorpayTestModeExecutor is a documented stub, not a working integration.
It should fail loudly and immediately without credentials, never silently
pretend to work.
"""
from __future__ import annotations

import pytest

from recoup.razorpay_adapter import RazorpayTestModeExecutor


def test_refuses_to_construct_without_credentials(monkeypatch):
    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    with pytest.raises(RuntimeError, match="RAZORPAY_KEY_ID"):
        RazorpayTestModeExecutor()
