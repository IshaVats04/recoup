"""Simulated execution of a chosen action -> observed outcome.

There is no real payment gateway here (this build intentionally uses only
synthetic data - see README). The success probabilities below are
illustrative, not fitted to real data, but they are diagnosis-aware by
design: picking the action that actually matches the root cause has a
higher chance of recovering the money than a mismatched one. That gap is
the entire point of the diagnose -> decide pipeline, and it's what the
smart-vs-baseline comparison in the report measures.
"""
from __future__ import annotations

import random

from .models import Action, Category, Event, Outcome, RootCause

MESSAGE_COST = 0.35  # INR, illustrative cost of one SMS/email/WhatsApp send
HUMAN_ESCALATION_COST = 45.0  # INR, illustrative cost of a human agent touch

# (category, root_cause, action) -> probability of recovering the money.
_SUCCESS_TABLE = {
    (Category.FAILED_PAYMENT, RootCause.ISSUER_TIMEOUT, Action.RETRY_NOW): 0.55,
    (Category.FAILED_PAYMENT, RootCause.ISSUER_TIMEOUT, Action.RETRY_BACKOFF): 0.80,
    (Category.FAILED_PAYMENT, RootCause.BANK_SERVER_ERROR, Action.RETRY_BACKOFF): 0.70,
    (Category.FAILED_PAYMENT, RootCause.BANK_SERVER_ERROR, Action.RETRY_NOW): 0.30,
    (Category.FAILED_PAYMENT, RootCause.INSUFFICIENT_FUNDS, Action.RETRY_NOW): 0.05,
    (Category.FAILED_PAYMENT, RootCause.INSUFFICIENT_FUNDS, Action.RETRY_BACKOFF): 0.32,
    (Category.FAILED_PAYMENT, RootCause.EXPIRED_CARD, Action.RETRY_NOW): 0.02,
    (Category.FAILED_PAYMENT, RootCause.EXPIRED_CARD, Action.SEND_UPDATE_PAYMENT_LINK): 0.58,
    (Category.FAILED_PAYMENT, RootCause.UPI_MANDATE_FAILED, Action.RETRY_BACKOFF): 0.25,
    (Category.FAILED_PAYMENT, RootCause.UPI_MANDATE_FAILED, Action.SEND_UPDATE_PAYMENT_LINK): 0.50,
    (Category.FAILED_PAYMENT, RootCause.RISK_BLOCK, Action.RETRY_NOW): 0.03,
    (Category.FAILED_PAYMENT, RootCause.UNKNOWN, Action.RETRY_NOW): 0.15,

    (Category.CHECKOUT_ABANDONMENT, RootCause.PRICE_SHOCK, Action.SEND_REMINDER_WITH_DISCOUNT): 0.40,
    (Category.CHECKOUT_ABANDONMENT, RootCause.PRICE_SHOCK, Action.SEND_REMINDER_IMMEDIATE): 0.10,
    (Category.CHECKOUT_ABANDONMENT, RootCause.MISSING_PAYMENT_METHOD, Action.SEND_PAYMENT_METHOD_NUDGE): 0.50,
    (Category.CHECKOUT_ABANDONMENT, RootCause.MISSING_PAYMENT_METHOD, Action.SEND_REMINDER_IMMEDIATE): 0.15,
    (Category.CHECKOUT_ABANDONMENT, RootCause.OTP_DELAY, Action.SEND_REMINDER_IMMEDIATE): 0.45,
    (Category.CHECKOUT_ABANDONMENT, RootCause.DISTRACTION, Action.SEND_REMINDER_IMMEDIATE): 0.28,
    (Category.CHECKOUT_ABANDONMENT, RootCause.UNKNOWN, Action.SEND_REMINDER_IMMEDIATE): 0.18,

    (Category.OVERDUE_INVOICE, RootCause.FORGOTTEN, Action.SEND_GENTLE_REMINDER): 0.58,
    (Category.OVERDUE_INVOICE, RootCause.FORGOTTEN, Action.SEND_FIRM_REMINDER): 0.45,
    (Category.OVERDUE_INVOICE, RootCause.CASH_FLOW_ISSUE, Action.OFFER_PAYMENT_PLAN): 0.52,
    (Category.OVERDUE_INVOICE, RootCause.CASH_FLOW_ISSUE, Action.SEND_FIRM_REMINDER): 0.14,
    (Category.OVERDUE_INVOICE, RootCause.UNKNOWN, Action.SEND_GENTLE_REMINDER): 0.28,
}

_DEFAULT_PROBABILITY = 0.12

_NO_OP_ACTIONS = {
    Action.WAIT_PROMISE_TO_PAY, Action.DEFER_DND, Action.WRITE_OFF,
    Action.GIVE_UP, Action.NO_ACTION_LOW_VALUE,
}


def simulate(event: Event, root_cause: RootCause, action: Action, rng: random.Random) -> Outcome:
    if action == Action.ESCALATE_HUMAN:
        return Outcome(
            recovered=False, amount_recovered=0.0, cost=HUMAN_ESCALATION_COST,
            note="handed to a human agent; outcome pending, not counted as an automated recovery",
        )

    if action in _NO_OP_ACTIONS:
        return Outcome(recovered=False, amount_recovered=0.0, cost=0.0,
                        note=f"no automated action taken ({action.value})")

    probability = _SUCCESS_TABLE.get((event.category, root_cause, action), _DEFAULT_PROBABILITY)
    cost = MESSAGE_COST if action.value.startswith(("send_", "offer_")) else 0.0
    recovered = rng.random() < probability
    amount_recovered = event.amount if recovered else 0.0
    return Outcome(
        recovered=recovered, amount_recovered=amount_recovered, cost=cost,
        note=f"P(success)={probability:.2f} for action '{action.value}' given cause '{root_cause.value}'",
    )
