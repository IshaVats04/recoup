"""Root-cause diagnosis: deterministic rules first, optional LLM only for
free-text notes that don't map to a structured code.

diagnose() always returns a Diagnosis - it never raises and never returns
None, so callers never need a null check.
"""
from __future__ import annotations

from . import llm as llm_module
from .models import Category, Diagnosis, Event, RootCause

_PAYMENT_CODE_MAP = {
    "insufficient_funds": RootCause.INSUFFICIENT_FUNDS,
    "expired_card": RootCause.EXPIRED_CARD,
    "issuer_timeout": RootCause.ISSUER_TIMEOUT,
    "risk_block": RootCause.RISK_BLOCK,
    "upi_mandate_failed": RootCause.UPI_MANDATE_FAILED,
    "bank_server_error": RootCause.BANK_SERVER_ERROR,
}

_SIGNAL_MAP = {
    "price_shock": RootCause.PRICE_SHOCK,
    "missing_payment_method": RootCause.MISSING_PAYMENT_METHOD,
    "otp_delay": RootCause.OTP_DELAY,
    "distraction": RootCause.DISTRACTION,
}

ALLOWED_ROOT_CAUSES_BY_CATEGORY = {
    Category.FAILED_PAYMENT: {
        RootCause.INSUFFICIENT_FUNDS, RootCause.EXPIRED_CARD, RootCause.ISSUER_TIMEOUT,
        RootCause.RISK_BLOCK, RootCause.UPI_MANDATE_FAILED, RootCause.BANK_SERVER_ERROR,
        RootCause.UNKNOWN,
    },
    Category.CHECKOUT_ABANDONMENT: {
        RootCause.PRICE_SHOCK, RootCause.MISSING_PAYMENT_METHOD, RootCause.OTP_DELAY,
        RootCause.DISTRACTION, RootCause.UNKNOWN,
    },
    Category.OVERDUE_INVOICE: {
        RootCause.FORGOTTEN, RootCause.CASH_FLOW_ISSUE, RootCause.DISPUTED, RootCause.UNKNOWN,
    },
}


def diagnose(event: Event, use_llm: bool = False) -> Diagnosis:
    if event.category == Category.FAILED_PAYMENT:
        if event.decline_code in _PAYMENT_CODE_MAP:
            return Diagnosis(
                root_cause=_PAYMENT_CODE_MAP[event.decline_code],
                confidence=0.95,
                rationale=f"structured decline code '{event.decline_code}'",
                source="rule",
            )
        if event.decline_note and use_llm:
            llm_result = llm_module.diagnose_with_llm(
                event, allowed=ALLOWED_ROOT_CAUSES_BY_CATEGORY[event.category]
            )
            if llm_result is not None:
                return llm_result
        return Diagnosis(
            root_cause=RootCause.UNKNOWN, confidence=0.3,
            rationale="no structured decline code, and no LLM diagnosis available", source="rule",
        )

    if event.category == Category.CHECKOUT_ABANDONMENT:
        cause = _SIGNAL_MAP.get(event.signal, RootCause.UNKNOWN)
        confidence = 0.8 if cause != RootCause.UNKNOWN else 0.3
        return Diagnosis(cause, confidence, f"abandonment signal '{event.signal}'", "rule")

    if event.category == Category.OVERDUE_INVOICE:
        if event.dispute_flag:
            return Diagnosis(RootCause.DISPUTED, 0.99, "invoice flagged as disputed", "rule")
        if event.prior_contact_count >= 2:
            return Diagnosis(
                RootCause.CASH_FLOW_ISSUE, 0.55,
                "multiple reminders already sent without payment", "rule",
            )
        if event.days_overdue <= 20 and event.prior_contact_count == 0:
            return Diagnosis(RootCause.FORGOTTEN, 0.6, "first overdue notice, likely just forgotten", "rule")
        return Diagnosis(RootCause.FORGOTTEN, 0.4, "default assumption pending more signal", "rule")

    return Diagnosis(RootCause.UNKNOWN, 0.1, "unrecognized category", "rule")
