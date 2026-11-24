"""Attack case loading and validation."""
from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import List, Optional

import yaml

CATEGORIES = {"direct_injection", "indirect_injection", "exfiltration", "filter_evasion"}
CHECK_TYPES = {"canary_in_output", "canary_obfuscated", "canary_in_email", "email_to_external", "tool_unauthorized"}
PLANT_WHERE = {"user", "document", "page", "customer_note"}


@dataclass
class Attack:
    id: str
    category: str
    title: str
    task: str
    plant: dict
    payload: str
    success: List[dict]
    authz: Optional[dict] = None
    tags: List[str] = field(default_factory=list)


def _validate(raw: dict) -> Attack:
    for key in ("id", "category", "title", "plant", "payload", "success"):
        if key not in raw:
            raise ValueError(f"attack {raw.get('id', '?')}: missing '{key}'")
    if raw["category"] not in CATEGORIES:
        raise ValueError(f"attack {raw['id']}: bad category {raw['category']}")
    if raw["plant"].get("where") not in PLANT_WHERE:
        raise ValueError(f"attack {raw['id']}: bad plant.where")
    for chk in raw["success"]:
        if chk.get("type") not in CHECK_TYPES:
            raise ValueError(f"attack {raw['id']}: bad check type {chk.get('type')}")
    if raw["plant"]["where"] != "user" and not raw.get("task"):
        raise ValueError(f"attack {raw['id']}: indirect attacks need a benign 'task'")
    return Attack(
        id=raw["id"], category=raw["category"], title=raw["title"], task=raw.get("task", ""),
        plant=raw["plant"], payload=raw["payload"], success=raw["success"],
        authz=raw.get("authz"), tags=raw.get("tags", []),
    )


def load_attacks(path: str) -> List[Attack]:
    files = sorted(glob.glob(os.path.join(path, "*.yaml"))) if os.path.isdir(path) else [path]
    attacks: List[Attack] = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            for raw in yaml.safe_load(fh) or []:
                attacks.append(_validate(raw))
    ids = [a.id for a in attacks]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate attack ids: {sorted(dupes)}")
    return attacks
