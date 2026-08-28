"""Append-only audit trail for every decision the agent makes."""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List

from .models import AuditRecord


def _record_to_row(record: AuditRecord) -> dict:
    return {
        "event_id": record.event.event_id,
        "category": record.event.category.value,
        "customer": record.event.display_name or record.event.customer_id,
        "amount": record.event.amount,
        "currency": record.event.currency,
        "policy": record.policy_name,
        "root_cause": record.diagnosis.root_cause.value if record.diagnosis else "",
        "diagnosis_source": record.diagnosis.source if record.diagnosis else "",
        "diagnosis_confidence": record.diagnosis.confidence if record.diagnosis else "",
        "action": record.decision.action.value,
        "reasoning": record.decision.reasoning,
        "guardrails_triggered": ";".join(g.name for g in record.decision.guardrails if g.triggered),
        "recovered": record.outcome.recovered,
        "amount_recovered": record.outcome.amount_recovered,
        "cost": record.outcome.cost,
        "outcome_note": record.outcome.note,
        "timestamp": record.timestamp.isoformat(),
    }


def write_csv(records: List[AuditRecord], path: Path) -> None:
    rows = [_record_to_row(r) for r in records]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def write_json(records: List[AuditRecord], path: Path) -> None:
    rows = [_record_to_row(r) for r in records]
    path.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")
