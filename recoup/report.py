"""Aggregate metrics and a self-contained HTML report.

The HTML file has no external dependencies (no CDN scripts, no fonts) so it
opens correctly straight from disk, offline, in any browser - useful for
recording the demo video without standing up a server.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import List, Tuple

from .models import AuditRecord


@dataclass
class CategoryMetrics:
    category: str
    count: int
    at_risk: float
    recovered: float
    cost: float

    @property
    def recovery_rate(self) -> float:
        return (self.recovered / self.at_risk * 100) if self.at_risk else 0.0


@dataclass
class BatchMetrics:
    label: str
    total_events: int
    at_risk: float
    recovered: float
    cost: float
    escalations: int
    write_offs: int
    deferred: int
    by_category: List[CategoryMetrics] = field(default_factory=list)
    guardrail_triggers: Counter = field(default_factory=Counter)

    @property
    def recovery_rate(self) -> float:
        return (self.recovered / self.at_risk * 100) if self.at_risk else 0.0

    @property
    def net_recovered(self) -> float:
        return self.recovered - self.cost


def compute_metrics(records: List[AuditRecord], label: str) -> BatchMetrics:
    at_risk_by_cat: dict = defaultdict(float)
    recovered_by_cat: dict = defaultdict(float)
    cost_by_cat: dict = defaultdict(float)
    count_by_cat: dict = defaultdict(int)
    guardrail_triggers: Counter = Counter()
    escalations = 0
    write_offs = 0
    deferred = 0
    total_at_risk = 0.0
    total_recovered = 0.0
    total_cost = 0.0

    for r in records:
        cat = r.event.category.value
        at_risk_by_cat[cat] += r.event.amount
        recovered_by_cat[cat] += r.outcome.amount_recovered
        cost_by_cat[cat] += r.outcome.cost
        count_by_cat[cat] += 1
        total_at_risk += r.event.amount
        total_recovered += r.outcome.amount_recovered
        total_cost += r.outcome.cost
        for g in r.decision.guardrails:
            if g.triggered:
                guardrail_triggers[g.name] += 1
        if r.decision.action.value == "escalate_human":
            escalations += 1
        elif r.decision.action.value == "write_off":
            write_offs += 1
        elif r.decision.action.value == "defer_dnd":
            deferred += 1

    by_category = [
        CategoryMetrics(cat, count_by_cat[cat], at_risk_by_cat[cat], recovered_by_cat[cat], cost_by_cat[cat])
        for cat in sorted(at_risk_by_cat)
    ]

    return BatchMetrics(
        label=label,
        total_events=len(records),
        at_risk=total_at_risk,
        recovered=total_recovered,
        cost=total_cost,
        escalations=escalations,
        write_offs=write_offs,
        deferred=deferred,
        by_category=by_category,
        guardrail_triggers=guardrail_triggers,
    )


def _bars(rows: List[Tuple[str, float, str]]) -> str:
    bar_height, gap = 18, 10
    y = 0
    parts: List[str] = []
    max_value = max((v for _, v, _ in rows), default=0) or 1
    for label, value, color in rows:
        w = (value / max_value) * 300
        parts.append(
            f'<text x="0" y="{y + bar_height - 5}" font-size="12" fill="#4b5563">{label}</text>'
            f'<rect x="150" y="{y}" width="{w:.1f}" height="{bar_height}" rx="3" fill="{color}"/>'
            f'<text x="{150 + w + 8:.1f}" y="{y + bar_height - 5}" font-size="12" fill="#111827">'
            f'&#8377;{value:,.0f}</text>'
        )
        y += bar_height + gap
    height = max(y, 1)
    return f'<svg viewBox="0 0 480 {height}" width="480" height="{height}">{"".join(parts)}</svg>'


def render_html(smart: BatchMetrics, baseline: BatchMetrics, sample: List[AuditRecord]) -> str:
    cat_rows = "".join(
        f"<tr><td>{m.category}</td><td>{m.count}</td>"
        f"<td>&#8377;{m.at_risk:,.0f}</td><td>&#8377;{m.recovered:,.0f}</td>"
        f"<td>{m.recovery_rate:.1f}%</td></tr>"
        for m in smart.by_category
    )

    guardrail_rows = "".join(
        f"<tr><td>{name}</td><td>{count}</td></tr>"
        for name, count in sorted(smart.guardrail_triggers.items(), key=lambda kv: -kv[1])
    ) or "<tr><td colspan='2'>none triggered</td></tr>"

    audit_rows = "".join(
        f"<tr><td>{r.event.event_id}</td><td>{r.event.category.value}</td>"
        f"<td>{r.diagnosis.root_cause.value if r.diagnosis else ''}</td>"
        f"<td>{r.decision.action.value}</td>"
        f"<td>{'yes' if r.outcome.recovered else 'no'}</td>"
        f"<td>&#8377;{r.outcome.amount_recovered:,.0f}</td>"
        f"<td>{r.decision.reasoning}</td></tr>"
        for r in sample
    )

    lift = smart.recovered - baseline.recovered
    rate_lift = smart.recovery_rate - baseline.recovery_rate

    comparison_svg = _bars([
        ("At risk", smart.at_risk, "#9ca3af"),
        ("Smart agent recovered", smart.recovered, "#b45309"),
        ("Naive baseline recovered", baseline.recovered, "#d1d5db"),
    ])

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Recoup - batch report</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; margin: 2rem auto;
         max-width: 920px; color: #111827; background: #fafaf9; line-height: 1.5; padding: 0 1rem; }}
  h1 {{ margin-bottom: 0.2rem; }}
  .sub {{ color: #6b7280; margin-top: 0; }}
  .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 1rem; margin: 1.5rem 0; }}
  .card {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: 1rem; background: white; }}
  .card .label {{ font-size: 0.8rem; color: #6b7280; text-transform: uppercase; letter-spacing: .03em; }}
  .card .value {{ font-size: 1.6rem; font-weight: 600; margin-top: .25rem; }}
  table {{ width: 100%; border-collapse: collapse; margin: 1rem 0 2rem; font-size: 0.85rem; }}
  th, td {{ text-align: left; padding: 0.5rem 0.6rem; border-bottom: 1px solid #e5e7eb; }}
  th {{ color: #6b7280; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; }}
  section {{ margin-bottom: 2rem; }}
  code {{ background: #f3f4f6; padding: 0.1rem 0.35rem; border-radius: 4px; }}
  .wrap {{ overflow-x: auto; }}
</style>
</head>
<body>
  <h1>Recoup &mdash; Revenue Recovery Agent</h1>
  <p class="sub">Batch report &middot; {smart.total_events} events &middot;
     &#8377;{smart.at_risk:,.0f} total revenue at risk</p>

  <div class="grid">
    <div class="card"><div class="label">Recovered (smart agent)</div>
      <div class="value">&#8377;{smart.recovered:,.0f}</div></div>
    <div class="card"><div class="label">Recovery rate</div>
      <div class="value">{smart.recovery_rate:.1f}%</div></div>
    <div class="card"><div class="label">Net of outreach cost</div>
      <div class="value">&#8377;{smart.net_recovered:,.0f}</div></div>
  </div>

  <section>
    <h2>Smart agent vs. naive baseline</h2>
    <p>The baseline applies the same single action to every event in a category, regardless of
       diagnosed root cause &mdash; e.g. always <code>retry_now</code> on a failed payment. Both
       policies obey the same compliance guardrails (dispute routing, high-value escalation,
       promise-to-pay, retry caps, DND hours). The only difference is whether the action is
       chosen based on a diagnosis.</p>
    <div class="wrap">{comparison_svg}</div>
    <div class="wrap">
    <table>
      <tr><th>Policy</th><th>Recovered</th><th>Rate</th><th>Cost</th><th>Net</th></tr>
      <tr><td>{smart.label}</td><td>&#8377;{smart.recovered:,.0f}</td><td>{smart.recovery_rate:.1f}%</td>
          <td>&#8377;{smart.cost:,.0f}</td><td>&#8377;{smart.net_recovered:,.0f}</td></tr>
      <tr><td>{baseline.label}</td><td>&#8377;{baseline.recovered:,.0f}</td><td>{baseline.recovery_rate:.1f}%</td>
          <td>&#8377;{baseline.cost:,.0f}</td><td>&#8377;{baseline.net_recovered:,.0f}</td></tr>
    </table>
    </div>
    <p><strong>Diagnosis-driven action selection recovered &#8377;{lift:,.0f} more</strong>
       than the naive baseline ({rate_lift:+.1f} percentage points of recovery rate).</p>
  </section>

  <section>
    <h2>By category</h2>
    <div class="wrap">
    <table>
      <tr><th>Category</th><th>Events</th><th>At risk</th><th>Recovered</th><th>Rate</th></tr>
      {cat_rows}
    </table>
    </div>
  </section>

  <section>
    <h2>Guardrails &amp; stopping rules triggered</h2>
    <div class="wrap">
    <table>
      <tr><th>Guardrail</th><th>Times triggered</th></tr>
      {guardrail_rows}
    </table>
    </div>
    <p>{smart.escalations} case(s) escalated to a human, {smart.write_offs} written off,
       {smart.deferred} deferred (DND / contact-frequency cap).</p>
  </section>

  <section>
    <h2>Audit trail (first {len(sample)} of {smart.total_events})</h2>
    <div class="wrap">
    <table>
      <tr><th>Event</th><th>Category</th><th>Root cause</th><th>Action</th>
          <th>Recovered</th><th>Amount</th><th>Reasoning</th></tr>
      {audit_rows}
    </table>
    </div>
    <p>Full trail: <code>out/audit_trail.csv</code> and <code>out/audit_trail.json</code>.</p>
  </section>
</body>
</html>"""
