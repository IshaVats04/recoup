"""Core data model for the Revenue Recovery Agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import List, Optional


class Category(str, Enum):
    FAILED_PAYMENT = "failed_payment"
    CHECKOUT_ABANDONMENT = "checkout_abandonment"
    OVERDUE_INVOICE = "overdue_invoice"


class RootCause(str, Enum):
    # failed_payment
    INSUFFICIENT_FUNDS = "insufficient_funds"
    EXPIRED_CARD = "expired_card"
    ISSUER_TIMEOUT = "issuer_timeout"
    RISK_BLOCK = "risk_block"
    UPI_MANDATE_FAILED = "upi_mandate_failed"
    BANK_SERVER_ERROR = "bank_server_error"
    # checkout_abandonment
    PRICE_SHOCK = "price_shock"
    MISSING_PAYMENT_METHOD = "missing_payment_method"
    OTP_DELAY = "otp_delay"
    DISTRACTION = "distraction"
    # overdue_invoice
    FORGOTTEN = "forgotten"
    CASH_FLOW_ISSUE = "cash_flow_issue"
    DISPUTED = "disputed"
    # fallback, any category
    UNKNOWN = "unknown"


class Action(str, Enum):
    RETRY_NOW = "retry_now"
    RETRY_BACKOFF = "retry_backoff"
    SEND_UPDATE_PAYMENT_LINK = "send_update_payment_link"
    OFFER_ALT_PAYMENT_METHOD = "offer_alt_payment_method"
    SEND_REMINDER_IMMEDIATE = "send_reminder_immediate"
    SEND_REMINDER_WITH_DISCOUNT = "send_reminder_with_discount"
    SEND_PAYMENT_METHOD_NUDGE = "send_payment_method_nudge"
    SEND_GENTLE_REMINDER = "send_gentle_reminder"
    SEND_FIRM_REMINDER = "send_firm_reminder"
    OFFER_PAYMENT_PLAN = "offer_payment_plan"
    ESCALATE_HUMAN = "escalate_human"
    WAIT_PROMISE_TO_PAY = "wait_promise_to_pay"
    DEFER_DND = "defer_dnd"
    WRITE_OFF = "write_off"
    GIVE_UP = "give_up"
    NO_ACTION_LOW_VALUE = "no_action_low_value"


@dataclass
class Event:
    event_id: str
    category: Category
    customer_id: str
    amount: float
    currency: str
    occurred_at: datetime
    display_name: Optional[str] = None

    # failed_payment fields
    payment_method: Optional[str] = None
    decline_code: Optional[str] = None
    decline_note: Optional[str] = None
    attempts_so_far: int = 0
    last_attempt_at: Optional[datetime] = None

    # checkout_abandonment fields
    abandonment_stage: Optional[str] = None
    signal: Optional[str] = None

    # overdue_invoice fields
    invoice_id: Optional[str] = None
    days_overdue: int = 0
    prior_contact_count: int = 0
    last_contacted_at: Optional[datetime] = None
    promise_to_pay_date: Optional[datetime] = None
    dispute_flag: bool = False


@dataclass
class Diagnosis:
    root_cause: RootCause
    confidence: float
    rationale: str
    source: str  # "rule" or "llm"


@dataclass
class GuardrailCheck:
    name: str
    triggered: bool
    detail: str


@dataclass
class Decision:
    action: Action
    reasoning: str
    guardrails: List[GuardrailCheck] = field(default_factory=list)


@dataclass
class Outcome:
    recovered: bool
    amount_recovered: float
    cost: float
    note: str


@dataclass
class AuditRecord:
    event: Event
    diagnosis: Optional[Diagnosis]
    decision: Decision
    outcome: Outcome
    policy_name: str
    timestamp: datetime
