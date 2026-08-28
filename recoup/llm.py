"""Optional LLM-assisted diagnosis and message drafting.

Disabled by default, and never required for the agent to run. The LLM (when
enabled) is only ever allowed to (a) classify an ambiguous free-text note
into one of a *fixed, whitelisted* set of root causes, and (b) draft
customer-facing copy for an action the deterministic policy has already
chosen. It never picks the action itself - see policy.py for why.

Enable with:
    pip install -r requirements-llm.txt
    export ANTHROPIC_API_KEY=...   # (or set it in the environment on Windows)
    python -m recoup.run --use-llm

Any failure here (missing package, missing key, network error, malformed
response, an out-of-whitelist answer) is swallowed and the caller falls
back to the deterministic rule-based path. A batch run must never crash
because an optional LLM call failed.
"""
from __future__ import annotations

import json
import os
from typing import Optional, Set

from .models import Diagnosis, Event, RootCause

_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")


def _client():
    try:
        import anthropic  # type: ignore
    except ImportError:
        return None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    return anthropic.Anthropic(api_key=api_key)


def diagnose_with_llm(event: Event, allowed: Set[RootCause]) -> Optional[Diagnosis]:
    """Classify an ambiguous decline note into one of `allowed` root causes.

    Returns None (never raises) if the LLM is unavailable, unreachable, or
    returns something outside the allowed set - the caller always has a
    rule-based fallback ready.
    """
    client = _client()
    if client is None:
        return None

    allowed_values = sorted(rc.value for rc in allowed)
    prompt = (
        "You are a payments root-cause classifier for an internal revenue-recovery agent.\n"
        f"Allowed root causes (choose exactly one, verbatim): {allowed_values}\n"
        f"Free-text failure note: {event.decline_note!r}\n"
        f"Structured context: payment_method={event.payment_method}, "
        f"attempts_so_far={event.attempts_so_far}\n"
        "Respond with ONLY a JSON object, no other text: "
        '{"root_cause": "<one of the allowed values>", "confidence": <0..1>, "rationale": "<short>"}'
    )
    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=200,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        raw_text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        )
        parsed = json.loads(raw_text.strip())
        root_cause_value = parsed["root_cause"]
        if root_cause_value not in allowed_values:
            return None  # bounded: never accept an answer outside the whitelist
        return Diagnosis(
            root_cause=RootCause(root_cause_value),
            confidence=float(parsed.get("confidence", 0.5)),
            rationale=str(parsed.get("rationale", ""))[:300],
            source="llm",
        )
    except Exception:
        return None


def draft_message(event: Event, root_cause: RootCause, action_label: str) -> Optional[str]:
    """Draft short customer-facing copy for an action the policy already chose.

    Returns None (never raises) if the LLM is unavailable - callers should
    fall back to a plain template string.
    """
    client = _client()
    if client is None:
        return None
    prompt = (
        "Draft a short (under 280 characters), polite, plain-English payment-recovery "
        f"message for a customer. Action being taken: '{action_label}'. "
        f"Likely reason: '{root_cause.value}'. Amount: {event.amount} {event.currency}. "
        "No emojis, no links, no placeholders. Return only the message text."
    )
    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=120,
            temperature=0.4,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", None) == "text"
        ).strip()
        return text or None
    except Exception:
        return None
