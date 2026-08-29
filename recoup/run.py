"""CLI entrypoint: generate a batch, run the smart agent and a naive baseline,
write the audit trail, and render a report.

Usage:
    python -m recoup.run
    python -m recoup.run --events 300 --seed 7 --use-llm
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from . import audit, report
from . import diagnose as diagnose_module
from .data_gen import generate_batch
from .models import AuditRecord, Event
from .policy import decide
from .simulate import RecoveryExecutor, SimulatedExecutor

if sys.platform == "win32":
    # Windows console codepages often can't encode the rupee sign; never let
    # that crash a run. (Console output below uses plain "Rs." regardless -
    # this is just a second layer of defense.)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run_policy(
    events: List[Event], *, smart: bool, use_llm: bool, now: datetime,
    draws: List[float], executor: RecoveryExecutor,
) -> List[AuditRecord]:
    """Run one policy (smart or naive baseline) over a batch.

    `draws` is one pre-generated uniform random number per event. Pass the
    *same* `draws` list to both the smart and baseline runs over the same
    `events` (see main() below) so that any difference in outcome is
    attributable to the difference in chosen action, not to the two runs
    independently getting luckier or unluckier random draws.
    """
    records: List[AuditRecord] = []
    for event, u in zip(events, draws):
        diagnosis = diagnose_module.diagnose(event, use_llm=use_llm if smart else False)
        decision = decide(event, diagnosis, now=now, smart=smart)
        outcome = executor.execute(event, diagnosis.root_cause, decision.action, u)
        records.append(AuditRecord(
            event=event, diagnosis=diagnosis, decision=decision, outcome=outcome,
            policy_name="smart" if smart else "naive_baseline", timestamp=now,
        ))
    return records


def _money(x: float) -> str:
    return f"Rs. {x:,.0f}"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Recoup - Revenue Recovery Agent batch runner")
    parser.add_argument("--events", type=int, default=200, help="number of synthetic events to generate")
    parser.add_argument("--seed", type=int, default=42, help="random seed, for a reproducible batch")
    parser.add_argument(
        "--use-llm", action="store_true",
        help="use Claude for ambiguous-note diagnosis + message drafting "
             "(requires ANTHROPIC_API_KEY; silently falls back to rules if unset/unreachable)",
    )
    parser.add_argument("--out", type=Path, default=Path("out"), help="output directory")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    now = datetime(2026, 8, 24, 15, 0, 0)

    events = generate_batch(n=args.events, seed=args.seed, now=now)

    executor = SimulatedExecutor()
    draw_rng = random.Random(args.seed)
    draws = [draw_rng.random() for _ in events]

    smart_records = run_policy(events, smart=True, use_llm=args.use_llm, now=now,
                                draws=draws, executor=executor)
    baseline_records = run_policy(events, smart=False, use_llm=False, now=now,
                                   draws=draws, executor=executor)

    audit.write_csv(smart_records, args.out / "audit_trail.csv")
    audit.write_json(smart_records, args.out / "audit_trail.json")

    smart_metrics = report.compute_metrics(smart_records, "Recoup (diagnosis-driven)")
    baseline_metrics = report.compute_metrics(baseline_records, "Naive baseline (same action every time)")

    html = report.render_html(smart_metrics, baseline_metrics, smart_records[:25])
    (args.out / "report.html").write_text(html, encoding="utf-8")

    print(f"Batch size: {smart_metrics.total_events} events, {_money(smart_metrics.at_risk)} at risk\n")
    print(f"{'Policy':<42}{'Recovered':>14}{'Rate':>9}{'Cost':>12}{'Net':>14}")
    for m in (smart_metrics, baseline_metrics):
        print(f"{m.label:<42}{_money(m.recovered):>14}{m.recovery_rate:>8.1f}%"
              f"{_money(m.cost):>12}{_money(m.net_recovered):>14}")

    lift = smart_metrics.recovered - baseline_metrics.recovered
    rate_lift = smart_metrics.recovery_rate - baseline_metrics.recovery_rate
    print(f"\nDiagnosis-driven policy recovered {_money(lift)} more than the naive baseline "
          f"({rate_lift:+.1f} points of recovery rate).")
    print(f"Guardrail triggers: {dict(smart_metrics.guardrail_triggers)}")
    print(f"\nWrote {args.out / 'audit_trail.csv'}")
    print(f"Wrote {args.out / 'audit_trail.json'}")
    print(f"Wrote {args.out / 'report.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
