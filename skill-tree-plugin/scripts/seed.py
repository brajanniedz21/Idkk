#!/usr/bin/env python3
"""Build a fresh PERSONAL_SKILL_TREE.json from the structure definition.

Every node starts at level 0 with zero XP and zero evidence. That is
deliberate: the seed defines the *shape* of the tree — what exists and what
depends on what — not any claim about what has been achieved. Levels are earned
through `skilltree.py apply`, never seeded.

Re-running this OVERWRITES the tree and destroys progression history. It is a
one-time bootstrap, not part of the daily loop.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import structure

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "PERSONAL_SKILL_TREE.json")


def build() -> dict:
    now = dt.date.today().isoformat()
    return {
        "schema_version": 1,
        "player": {"name": "Brajan", "created": now, "last_update": None,
                   "player_level": 0, "total_xp": 0},
        "build": {
            "primary_class": None, "secondary_class": None, "creative_class": None,
            "confidence": "none",
            "note": "Left empty on purpose. A build is read off sustained behaviour "
                    "over months; naming one early makes the tree describe an "
                    "aspiration rather than a person.",
        },
        "attributes": {},
        "trees": [{"id": tid, "name": name, "description": desc, "status": "active"}
                  for tid, name, desc in structure.TREES],
        "nodes": structure.build_nodes(now),
        "milestones": [{"id": mid, "name": name, "requirement": req,
                        "unlocked": False, "date": None}
                       for mid, name, req in structure.MILESTONES],
        "quests": [],
        "interest_signals": [],
        "history": [],
    }


if __name__ == "__main__":
    if os.path.exists(OUT) and "--force" not in sys.argv:
        print(f"{OUT} already exists. Re-seeding destroys all progression history.\n"
              f"Pass --force if that is genuinely what you want.")
        sys.exit(1)
    tree = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(tree, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print(f"Seeded {OUT} with {len(tree['nodes'])} nodes across {len(tree['trees'])} "
          f"trees, {len(tree['milestones'])} milestones, all at level 0.")
