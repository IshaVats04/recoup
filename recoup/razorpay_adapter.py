"""A real-Razorpay-test-mode RecoveryExecutor - documented, NOT wired up.

This file exists to make the "production adapter can be swapped in" claim
concrete rather than aspirational: it shows exactly which actions would
need a real API call and what each one would need, without requiring a
Razorpay account, API keys, or a live network call anywhere in this repo's
default path. The synthetic-data build (SimulatedExecutor, in simulate.py)
is what actually runs and is tested - this class intentionally raises
NotImplementedError instead of pretending to be a working integration.

To make this real:
    pip install razorpay
    export RAZORPAY_KEY_ID=...        (your own test-mode credentials)
    export RAZORPAY_KEY_SECRET=...
and fill in the TODOs below with real razorpay-python SDK calls, then pass
RazorpayTestModeExecutor() into run_policy() instead of SimulatedExecutor()
- everything upstream of the executor (diagnose, decide, audit, report)
stays exactly the same, which is the point of the RecoveryExecutor seam.
"""
from __future__ import annotations

import os

from .models import Action, Event, Outcome, RootCause
from .simulate import RecoveryExecutor


class RazorpayTestModeExecutor(RecoveryExecutor):
    """Sketch of a real integration. Every branch below is an honest TODO."""

    def __init__(self) -> None:
        key_id = os.environ.get("RAZORPAY_KEY_ID")
        key_secret = os.environ.get("RAZORPAY_KEY_SECRET")
        if not key_id or not key_secret:
            raise RuntimeError(
                "RazorpayTestModeExecutor needs RAZORPAY_KEY_ID and "
                "RAZORPAY_KEY_SECRET - your own Razorpay test-mode "
                "credentials. This repo never supplies, stores, or asks "
                "you to paste those anywhere; you'd set them yourself. "
                "This class is a documented stub, not a working "
                "integration - see the module docstring."
            )
        try:
            import razorpay  # type: ignore
        except ImportError as exc:
            raise RuntimeError("pip install razorpay to use this executor") from exc
        self._client = razorpay.Client(auth=(key_id, key_secret))

    def execute(self, event: Event, root_cause: RootCause, action: Action, u: float) -> Outcome:
        if action in (Action.RETRY_NOW, Action.RETRY_BACKOFF):
            # TODO: call Razorpay's payment-retry / UPI mandate
            # re-authorization endpoint for `event.event_id` here, via
            # self._client, and map its response to an Outcome.
            raise NotImplementedError("wire up Razorpay's payment-retry API here")

        if action == Action.SEND_UPDATE_PAYMENT_LINK:
            # TODO: self._client.payment_link.create({...}) and send the
            # resulting link through whatever notification channel you use.
            raise NotImplementedError("wire up Razorpay Payment Links API here")

        if action in (
            Action.SEND_REMINDER_IMMEDIATE, Action.SEND_REMINDER_WITH_DISCOUNT,
            Action.SEND_PAYMENT_METHOD_NUDGE, Action.SEND_GENTLE_REMINDER,
            Action.SEND_FIRM_REMINDER, Action.OFFER_PAYMENT_PLAN, Action.OFFER_ALT_PAYMENT_METHOD,
        ):
            # TODO: Razorpay doesn't send customer messages itself - call
            # your SMS/email/WhatsApp provider here, then track delivery
            # and (async, via webhook) eventual payment confirmation.
            raise NotImplementedError("wire up a notification provider here")

        raise NotImplementedError(
            f"'{action.value}' has no real-world action (it's a no-op/escalation "
            "guardrail outcome) - route it to your human queue instead of here"
        )
