"""Root-cause diagnosis: rule-based mapping should be deterministic and total."""
from __future__ import annotations

from datetime import datetime

from recoup.diagnose import diagnose
from recoup.models import Category, Event, RootCause

NOW = datetime(2026, 8, 24, 15, 0, 0)


def _payment(decline_code=None, decline_note=None) -> Event:
    return Event(
        event_id="PAY", category=Category.FAILED_PAYMENT, customer_id="C1",
        amount=1_000.0, currency="INR", occurred_at=NOW,
        decline_code=decline_code, decline_note=decline_note,
    )


def test_structured_decline_codes_map_deterministically():
    cases = [
        ("insufficient_funds", RootCause.INSUFFICIENT_FUNDS),
        ("expired_card", RootCause.EXPIRED_CARD),
        ("issuer_timeout", RootCause.ISSUER_TIMEOUT),
        ("risk_block", RootCause.RISK_BLOCK),
        ("upi_mandate_failed", RootCause.UPI_MANDATE_FAILED),
        ("bank_server_error", RootCause.BANK_SERVER_ERROR),
    ]
    for code, expected in cases:
        diagnosis = diagnose(_payment(decline_code=code), use_llm=False)
        assert diagnosis.root_cause == expected
        assert diagnosis.source == "rule"


def test_ambiguous_note_without_llm_falls_back_to_unknown():
    event = _payment(decline_note="customer says card is fine but it keeps failing")
    diagnosis = diagnose(event, use_llm=False)
    assert diagnosis.root_cause == RootCause.UNKNOWN
    assert diagnosis.source == "rule"


def test_checkout_signals_map_to_expected_causes():
    event = Event(
        event_id="CART", category=Category.CHECKOUT_ABANDONMENT, customer_id="C1",
        amount=1_000.0, currency="INR", occurred_at=NOW, signal="price_shock",
    )
    diagnosis = diagnose(event, use_llm=False)
    assert diagnosis.root_cause == RootCause.PRICE_SHOCK


def test_disputed_invoice_is_always_disputed_regardless_of_other_signals():
    event = Event(
        event_id="INV", category=Category.OVERDUE_INVOICE, customer_id="C1",
        amount=1_000.0, currency="INR", occurred_at=NOW,
        days_overdue=5, prior_contact_count=3, dispute_flag=True,
    )
    diagnosis = diagnose(event, use_llm=False)
    assert diagnosis.root_cause == RootCause.DISPUTED
    assert diagnosis.confidence > 0.9
