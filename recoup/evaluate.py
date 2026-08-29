"""Multi-batch evaluation: run many independent batches and report averaged
smart-vs-baseline results, instead of a single seed's point estimate.

A single `python -m recoup.run --seed 7` run proves the idea works once.
This proves it holds up: same comparison, repeated across many independent
random batches, reporting the average lift and how consistently the smart
policy wins - not just one number that could look cherry-picked even when
it isn't.

Usage:
    python -m recoup.evaluate
    python -m recoup.evaluate --batches 100 --events-per-batch 500
"""
from __future__ import annotations

import argparse
import random
import statistics
import sys
from datetime import datetime
from typing import List, Optional

from .data_gen import generate_batch
from .report import compute_metrics
from .run import run_policy
from .simulate import SimulatedExecutor

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Recoup - multi-batch evaluation")
    parser.add_argument("--batches", type=int, default=100)
    parser.add_argument("--events-per-batch", type=int, default=500)
    parser.add_argument("--base-seed", type=int, default=1000,
                         help="each batch uses base-seed + its index, so the run is reproducible")
    args = parser.parse_args(argv)

    now = datetime(2026, 8, 24, 15, 0, 0)
    executor = SimulatedExecutor()

    smart_rates: List[float] = []
    baseline_rates: List[float] = []
    total_events = 0

    for i in range(args.batches):
        seed = args.base_seed + i
        events = generate_batch(n=args.events_per_batch, seed=seed, now=now)
        total_events += len(events)

        draw_rng = random.Random(seed)
        draws = [draw_rng.random() for _ in events]

        smart = run_policy(events, smart=True, use_llm=False, now=now, draws=draws, executor=executor)
        baseline = run_policy(events, smart=False, use_llm=False, now=now, draws=draws, executor=executor)

        smart_rates.append(compute_metrics(smart, "smart").recovery_rate)
        baseline_rates.append(compute_metrics(baseline, "baseline").recovery_rate)

    smart_mean = statistics.mean(smart_rates)
    baseline_mean = statistics.mean(baseline_rates)
    wins = sum(1 for s, b in zip(smart_rates, baseline_rates) if s > b)

    print(f"Ran {args.batches} batches x {args.events_per_batch} events "
          f"({total_events:,} events total)\n")
    print(f"Smart average recovery rate:   {smart_mean:5.1f}%  "
          f"(min {min(smart_rates):.1f}%, max {max(smart_rates):.1f}%)")
    print(f"Naive average recovery rate:   {baseline_mean:5.1f}%  "
          f"(min {min(baseline_rates):.1f}%, max {max(baseline_rates):.1f}%)")
    print(f"\nIncremental recovery:          {smart_mean - baseline_mean:+.1f} percentage points")
    print(f"Smart beat naive in {wins}/{args.batches} batches ({wins / args.batches * 100:.0f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
