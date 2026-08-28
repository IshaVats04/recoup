"""Synthetic batch generator for at-risk revenue events.

Everything here is deterministic given a seed, so a batch (and therefore a
report) is fully reproducible. No external accounts or network access are
needed to generate or process a batch.
"""
from __future__ import annotations

import random
import string
from datetime import datetime, timedelta
from typing import List, Optional

from .models import Category, Event

FIRST_NAMES = [
    "Aarav", "Vihaan", "Ishaan", "Priya", "Ananya", "Diya", "Rohan",
    "Kabir", "Meera", "Sara", "Aditya", "Neha", "Vikram", "Zoya",
]
BUSINESS_SUFFIXES = [
    "Traders", "Retail", "Textiles", "Foods", "Electronics",
    "Logistics", "Apparel", "Studio",
]

DECLINE_CODES = [
    "insufficient_funds", "expired_card", "issuer_timeout",
    "risk_block", "upi_mandate_failed", "bank_server_error",
]

# A handful of realistic free-text notes that don't map to a structured
# decline code. These exist to exercise the ambiguous-note / optional
# LLM-assisted diagnosis path.
AMBIGUOUS_NOTES = [
    "customer says card is fine but payment keeps failing, tried twice",
    "agent note: bank app showed 'declined by issuer', reason unclear",
    "customer messaged saying they think their bank blocked an international flag",
    "support chat: 'it just says try again later, no idea why'",
]

PAYMENT_METHODS = ["card", "upi", "netbanking"]
ABANDONMENT_STAGES = ["payment_page", "otp_page", "review_page"]
ABANDONMENT_SIGNALS = ["price_shock", "missing_payment_method", "otp_delay", "distraction"]


def _rand_id(rng: random.Random, prefix: str, n: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    return f"{prefix}_{''.join(rng.choices(chars, k=n))}"


def _gen_failed_payment(rng: random.Random, now: datetime) -> Event:
    code = rng.choice(DECLINE_CODES)
    note = rng.choice(AMBIGUOUS_NOTES) if rng.random() < 0.15 else None
    attempts = rng.choices([0, 1, 2, 3], weights=[55, 25, 12, 8])[0]
    occurred = now - timedelta(hours=rng.uniform(0, 96))
    last_attempt = occurred if attempts == 0 else occurred + timedelta(hours=rng.uniform(1, 20))
    return Event(
        event_id=_rand_id(rng, "PAY"),
        category=Category.FAILED_PAYMENT,
        customer_id=_rand_id(rng, "CUST", 6),
        amount=round(rng.uniform(299, 45_000), 2),
        currency="INR",
        occurred_at=occurred,
        display_name=rng.choice(FIRST_NAMES),
        payment_method=rng.choice(PAYMENT_METHODS),
        decline_code=code,
        decline_note=note,
        attempts_so_far=attempts,
        last_attempt_at=last_attempt,
    )


def _gen_checkout_abandonment(rng: random.Random, now: datetime) -> Event:
    occurred = now - timedelta(hours=rng.uniform(0, 72))
    return Event(
        event_id=_rand_id(rng, "CART"),
        category=Category.CHECKOUT_ABANDONMENT,
        customer_id=_rand_id(rng, "CUST", 6),
        amount=round(rng.uniform(199, 12_000), 2),
        currency="INR",
        occurred_at=occurred,
        display_name=rng.choice(FIRST_NAMES),
        abandonment_stage=rng.choice(ABANDONMENT_STAGES),
        signal=rng.choice(ABANDONMENT_SIGNALS),
    )


def _gen_overdue_invoice(rng: random.Random, now: datetime) -> Event:
    bucket = rng.choices(
        [rng.randint(1, 15), rng.randint(16, 45), rng.randint(46, 90), rng.randint(91, 150)],
        weights=[45, 30, 15, 10],
    )[0]
    occurred = now - timedelta(days=bucket)
    prior_contacts = rng.choices([0, 1, 2, 3], weights=[40, 30, 20, 10])[0]
    promise_date = None
    if prior_contacts > 0 and rng.random() < 0.25:
        promise_date = now + timedelta(days=rng.randint(1, 10))
    dispute = rng.random() < 0.08
    business = f"{rng.choice(FIRST_NAMES)} {rng.choice(BUSINESS_SUFFIXES)}"
    return Event(
        event_id=_rand_id(rng, "INV"),
        category=Category.OVERDUE_INVOICE,
        customer_id=_rand_id(rng, "CUST", 6),
        amount=round(rng.uniform(2_000, 250_000), 2),
        currency="INR",
        occurred_at=occurred,
        display_name=business,
        invoice_id=_rand_id(rng, "INVID", 6),
        days_overdue=bucket,
        prior_contact_count=prior_contacts,
        promise_to_pay_date=promise_date,
        dispute_flag=dispute,
    )


def generate_batch(n: int = 200, seed: int = 42, now: Optional[datetime] = None) -> List[Event]:
    """Generate a deterministic, mixed batch of at-risk revenue events."""
    rng = random.Random(seed)
    now = now or datetime(2026, 8, 24, 15, 0, 0)
    generators = [_gen_failed_payment, _gen_checkout_abandonment, _gen_overdue_invoice]
    weights = [0.45, 0.35, 0.20]
    events: List[Event] = []
    for _ in range(n):
        gen = rng.choices(generators, weights=weights)[0]
        events.append(gen(rng, now))
    events.sort(key=lambda e: e.occurred_at)
    return events
