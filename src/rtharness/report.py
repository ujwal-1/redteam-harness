"""Aggregate results into attack success rates and render markdown reports."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Dict, List


def _rate(num: int, den: int) -> float:
    return 100.0 * num / den if den else 0.0


def summarize(run: dict) -> dict:
    by_cat: Dict[str, Dict[str, int]] = defaultdict(lambda: {"runs": 0, "success": 0, "attempted": 0})
    by_mut: Dict[str, Dict[str, int]] = defaultdict(lambda: {"runs": 0, "success": 0, "attempted": 0})
    total = {"runs": 0, "success": 0, "attempted": 0}
    for r in run["results"]:
        for bucket in (by_cat[r["category"]], by_mut[r["mutator"]], total):
            bucket["runs"] += 1
            bucket["success"] += int(r["success"])
            bucket["attempted"] += int(r["attempted"])
    return {"total": total, "by_category": dict(by_cat), "by_mutator": dict(by_mut)}


def _table(title: str, buckets: Dict[str, Dict[str, int]]) -> List[str]:
    lines = [f"| {title} | Runs | Succeeded | Attempted | Attack success rate |", "|---|---|---|---|---|"]
    for name in sorted(buckets):
        b = buckets[name]
        lines.append(f"| {name} | {b['runs']} | {b['success']} | {b['attempted']} | {_rate(b['success'], b['runs']):.1f}% |")
    return lines


def render_markdown(run: dict, max_examples: int = 5) -> str:
    meta, s = run["meta"], summarize(run)
    t = s["total"]
    out = [
        "# Red-team report",
        "",
        f"- Backend: `{meta['backend']}` model: `{meta['model']}`",
        f"- Defense: `{meta['defense']}`",
        f"- Base attacks: {meta['base_attacks']}, mutators: {', '.join(meta['mutators'])}, trials: {meta['trials']}",
        f"- Total runs: {t['runs']}",
        "",
        f"**Overall attack success rate: {_rate(t['success'], t['runs']):.1f}%** "
        f"({t['success']} of {t['runs']} runs). "
        f"The model was fooled (attempted) in {_rate(t['attempted'], t['runs']):.1f}% of runs; "
        "the gap between attempted and succeeded is what the defenses stopped.",
        "",
    ]
    if meta["backend"] == "mock":
        out += ["> Mock backend: validates the harness only. These numbers say nothing about real models.", ""]
    out += _table("Category", s["by_category"]) + [""] + _table("Mutator", s["by_mutator"]) + [""]
    wins = [r for r in run["results"] if r["success"]][:max_examples]
    out.append("## Successful attacks (examples)")
    out.append("")
    if not wins:
        out.append("None.")
    for r in wins:
        out += [f"### {r['attack_id']} ({r['mutator']}): {r['title']}", "",
                f"Matched check: `{r['matched']}`", "", "```"]
        for m in r["messages"]:
            out.append(f"[{m['role']}] {m['content'][:300]}")
        out += ["```", ""]
    return "\n".join(out)


def render_compare(before: dict, after: dict) -> str:
    sb, sa = summarize(before), summarize(after)
    out = [
        "# Before / after",
        "",
        f"Before: defense `{before['meta']['defense']}`. After: defense `{after['meta']['defense']}`.",
        "",
        "| Category | Before | After | Change |",
        "|---|---|---|---|",
    ]
    cats = sorted(set(sb["by_category"]) | set(sa["by_category"]))
    for c in cats + ["TOTAL"]:
        b = sb["total"] if c == "TOTAL" else sb["by_category"].get(c, {"runs": 0, "success": 0})
        a = sa["total"] if c == "TOTAL" else sa["by_category"].get(c, {"runs": 0, "success": 0})
        rb, ra = _rate(b["success"], b["runs"]), _rate(a["success"], a["runs"])
        out.append(f"| {c} | {rb:.1f}% | {ra:.1f}% | {ra - rb:+.1f} pts |")
    return "\n".join(out)


def save_json(run: dict, path: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=2)
