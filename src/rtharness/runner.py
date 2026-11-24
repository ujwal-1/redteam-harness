"""Run every attack x mutator x trial against a backend and collect objective results."""
from __future__ import annotations

from dataclasses import asdict
from typing import Dict, List, Optional

from .agent import Defenses, run_agent
from .attacks import Attack
from .backends import Backend
from .judge import judge
from .mutators import MUTATORS
from .scenario import Scenario


def run_suite(backend: Backend, attacks: List[Attack], defenses: Defenses, mutators: List[str],
              trials: int = 1, seed: int = 0, progress: Optional[callable] = None) -> dict:
    unknown = [m for m in mutators if m not in MUTATORS]
    if unknown:
        raise SystemExit(f"unknown mutator(s): {unknown}; available: {sorted(MUTATORS)}")
    results: List[Dict] = []
    total = len(attacks) * len(mutators) * trials
    done = 0
    for atk in attacks:
        for mut in mutators:
            payload = MUTATORS[mut](atk.payload)
            for t in range(trials):
                sc = Scenario.build(seed + t, atk.plant, payload, atk.authz)
                task = payload if atk.plant["where"] == "user" else atk.task
                try:
                    tr = run_agent(backend, sc, task, defenses)
                    success, attempted, matched = judge(atk.success, tr, sc)
                except Exception as err:
                    tr = None
                    success, attempted, matched = False, False, f"error: {type(err).__name__}"
                results.append({
                    "attack_id": atk.id, "category": atk.category, "title": atk.title,
                    "mutator": mut, "trial": t, "success": success, "attempted": attempted,
                    "matched": matched, "final": tr.final if tr else "[ERROR: model request failed]",
                    "tool_calls": [asdict(c) for c in tr.tool_calls] if tr else [],
                    "messages": tr.messages if tr else [],
                })
                done += 1
                if progress:
                    progress(done, total)
    return {
        "meta": {"backend": backend.name, "model": getattr(backend, "model", None),
                 "defense": defenses.label(), "mutators": mutators, "trials": trials,
                 "seed": seed, "base_attacks": len(attacks), "total_runs": len(results)},
        "results": results,
    }
