"""A single, narrated run through the full pipeline on one illustrative,
ambiguous event - for demos. Prints each stage explicitly, so the AI
diagnosis step is a visible, inspectable part of the demo instead of
something that only shows up as a number in an aggregate report.

Usage:
    python -m recoup.trace
    python -m recoup.trace --use-llm      (requires ANTHROPIC_API_KEY)
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from typing import List, Optional

from . import diagnose as diagnose_module
from .models import Category, Event
from .policy import decide
from .simulate import SimulatedExecutor

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

EXAMPLE_EVENT = Event(
    event_id="PAY_DEMO",
    category=Category.FAILED_PAYMENT,
    customer_id="CUST_DEMO",
    amount=2_499.0,
    currency="INR",
    occurred_at=datetime(2026, 8, 24, 15, 0, 0),
    display_name="Rohan",
    payment_method="upi",
    decline_note="I've tried paying twice but UPI keeps failing.",
    attempts_so_far=0,
)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Recoup - one-event pipeline trace, for demos")
    parser.add_argument("--use-llm", action="store_true",
                         help="actually call Claude for this event's diagnosis "
                              "(requires ANTHROPIC_API_KEY; falls back to the rule "
                              "engine silently if it's unavailable, same as everywhere else)")
    parser.add_argument("--seed", type=int, default=0,
                         help="fixes the simulated outcome's random draw, for a reproducible demo")
    args = parser.parse_args(argv)

    event = EXAMPLE_EVENT
    now = event.occurred_at

    print(f"Event: failed UPI payment, Rs. {event.amount:,.0f}")
    print(f'Note:  "{event.decline_note}"')
    print("  |")
    print("  v")

    diagnosis = diagnose_module.diagnose(event, use_llm=args.use_llm)
    diagnosed_by = "Claude" if diagnosis.source == "llm" else "rule engine (no LLM diagnosis available)"
    print(diagnosed_by)
    print(f"  -> root_cause: {diagnosis.root_cause.value}")
    print(f"  -> confidence: {diagnosis.confidence:.2f}")
    print(f"  -> rationale:  {diagnosis.rationale}")
    print("  |")
    print("  v")

    decision = decide(event, diagnosis, now=now, smart=True)
    print("Policy")
    for g in decision.guardrails:
        status = "TRIGGERED" if g.triggered else "passed"
        print(f"  -> guardrail '{g.name}': {status}")
    print(f"  -> action: {decision.action.value}")
    print("  |")
    print("  v")

    u = random.Random(args.seed).random()
    outcome = SimulatedExecutor().execute(event, diagnosis.root_cause, decision.action, u)
    print("Simulated outcome")
    print(f"  -> recovered: {outcome.recovered}")
    print(f"  -> amount:    Rs. {outcome.amount_recovered:,.0f}")
    print(f"  -> note:      {outcome.note}")

    if not args.use_llm:
        print("\n(Run with --use-llm, with ANTHROPIC_API_KEY set, to see Claude do this")
        print(" classification for real instead of the rule-engine fallback shown above.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
