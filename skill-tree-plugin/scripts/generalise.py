#!/usr/bin/env python3
"""One-time migration: fold the 155-node tree into the coarser structure.

The tree was originally split far too fine — "Stippling" and "Recovery & Sleep"
as separate skills is a level of precision nobody can honestly assess about
themselves. This merges related nodes into broader ones.

Evidence is never discarded. Every dated event moves to its new node with its
kind, XP and reason intact, so any level still traces to the specific things
that earned it. XP is summed rather than averaged: a broader skill genuinely
holds all the work its narrower parts held, and the evidence-class ceiling still
applies afterwards, so nothing can be promoted past what the evidence supports.

Run once. It refuses to touch a tree that is already migrated.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import structure  # noqa: E402
from skilltree import recompute_all, save_tree  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TREE_PATH = os.path.join(ROOT, "data", "PERSONAL_SKILL_TREE.json")

# old node id -> new node id. Every id in the old tree must appear here.
MAP = {
    # Business & Growth
    "ent.fundamentals": "biz.fundamentals",
    "ent.offer": "biz.offer", "ent.pricing": "biz.offer", "ent.positioning": "biz.offer",
    "ent.copywriting": "biz.copywriting",
    "ent.acquisition": "biz.outreach",
    "ent.sales": "biz.sales",
    "ent.delivery": "biz.delivery", "ent.operations": "biz.delivery",
    "ent.scaling": "biz.scaling", "gro.architect": "biz.scaling",
    "ent.market_research": "biz.growth", "gro.diagnosis": "biz.growth",
    "gro.funnel": "biz.growth", "gro.conversion": "biz.growth",
    "gro.experiments": "biz.growth", "gro.strategy": "biz.growth",
    "gro.revops": "biz.growth",
    "gro.crm": "biz.crm", "gro.leads": "biz.crm",
    "gro.operator": "cross.ai_growth_operator",

    # AI & Automation
    "ai.fundamentals": "ai.fundamentals", "ai.local": "ai.fundamentals",
    "ai.prompting": "ai.prompting", "ai.context": "ai.prompting",
    "ai.claude_code": "ai.prompting", "ai.cost": "ai.prompting",
    "ai.agents": "ai.agents", "ai.orchestration": "ai.agents",
    "auto.fundamentals": "auto.fundamentals",
    "auto.zapier": "auto.tools", "auto.n8n": "auto.tools",
    "auto.multistep": "auto.integration", "auto.apis": "auto.integration",
    "auto.webhooks": "auto.integration",
    "auto.crm_integration": "auto.systems", "auto.cross_platform": "auto.systems",
    "auto.architecture": "auto.systems",
    "auto.production": "auto.production",
    "ai.prod_systems": "ai.production", "ai.unknown_1": "ai.production",

    # Content
    "yt.fundamentals": "yt.fundamentals", "yt.formats": "yt.fundamentals",
    "yt.ideas": "yt.ideas",
    "yt.titles": "yt.packaging", "yt.thumbnails": "yt.packaging",
    "yt.hooks": "yt.packaging",
    "yt.analytics": "yt.analytics", "yt.competitor": "yt.analytics",
    "yt.strategy": "yt.strategy",
    "yt.pipeline": "yt.systems", "yt.growth_operator": "yt.systems",

    # Visual & Creative
    "art.observation": "vis.drawing", "art.proportion": "vis.drawing",
    "art.shading": "vis.drawing", "art.media": "vis.drawing",
    "art.stippling": "vis.drawing", "art.digital": "vis.drawing",
    "art.character": "vis.drawing", "art.environment": "vis.drawing",
    "art.composition": "vis.composition", "art.perspective": "vis.composition",
    "film.composition": "vis.composition",
    "art.brand_design": "vis.brand",
    "film.storytelling": "vis.story",
    "film.cinematography": "vis.camera", "film.lighting": "vis.camera",
    "film.camera": "vis.camera",
    "film.editing": "vis.edit", "film.colour": "vis.edit", "film.sound": "vis.edit",
    "film.3d": "vis.3d", "film.environment": "vis.3d", "film.animation": "vis.3d",
    "film.vfx": "vis.3d",
    "film.ai_video": "vis.ai_video",
    "art.style": "vis.masterwork", "film.short": "vis.masterwork",
    "film.3d_production": "vis.masterwork",

    # Technology
    "tech.computing": "tech.computing", "tech.git": "tech.computing",
    "tech.html": "tech.frontend", "tech.js": "tech.frontend",
    "tech.python": "tech.code", "tech.apis": "tech.code", "tech.databases": "tech.code",
    "tech.web": "tech.web", "tech.dashboards": "tech.web",
    "tech.cloud": "tech.hosting", "tech.rpi": "tech.hosting",
    "tech.servers": "tech.hosting",
    "tech.ai_integration": "tech.ai_integration",
    "tech.architecture": "tech.architecture",

    # Fitness
    "fit.technique": "fit.training", "fit.knowledge": "fit.training",
    "fit.overload": "fit.progression", "fit.hypertrophy": "fit.progression",
    "fit.strength": "fit.progression", "fit.calisthenics": "fit.progression",
    "fit.nutrition": "fit.nutrition", "fit.macros": "fit.nutrition",
    "fit.meal_planning": "fit.nutrition",
    "fit.recovery": "fit.recovery",
    "fit.consistency": "fit.consistency",
    "fit.programming": "fit.programming", "fit.physique": "fit.programming",

    # Money
    "mon.literacy": "mon.literacy",
    "mon.budgeting": "mon.personal", "mon.saving": "mon.personal",
    "life.money_mgmt": "mon.personal",
    "mon.income": "mon.income", "mon.business_income": "mon.income",
    "mon.investing": "mon.investing", "mon.risk": "mon.investing",
    "mon.trading_knowledge": "mon.investing", "mon.trading_ability": "mon.investing",
    "mon.entrepreneurial_finance": "mon.business_finance",
    "mon.independence": "mon.independence",

    # Learning
    "lrn.research": "lrn.research",
    "lrn.critical": "lrn.thinking", "lrn.problem_solving": "lrn.thinking",
    "lrn.self_teaching": "lrn.self_teaching", "lrn.project_based": "lrn.self_teaching",
    "lrn.synthesis": "lrn.synthesis", "lrn.knowledge_mgmt": "lrn.synthesis",
    "lrn.experimentation": "lrn.experimentation",
    "lrn.systems_thinking": "lrn.systems", "lrn.rapid": "lrn.systems",
    "lrn.cross_domain": "lrn.systems",

    # Discipline & Independence
    "pd.reflection": "pd.reflection", "pd.journaling": "pd.reflection",
    "pd.self_awareness": "pd.reflection", "pd.decisions": "pd.reflection",
    "pd.confidence": "pd.reflection",
    "pd.planning": "pd.planning", "pd.focus": "pd.planning",
    "pd.consistency": "pd.consistency", "pd.discipline": "pd.consistency",
    "pd.delayed_gratification": "pd.consistency",
    "life.communication": "life.communication",
    "life.organisation": "life.organisation", "life.scheduling": "life.organisation",
    "life.admin": "life.organisation", "life.travel": "life.organisation",
    "life.cooking": "life.selfcare",
    "life.employment": "life.work", "life.business_admin": "life.work",
    "life.contracts": "life.work",
    "life.housing": "life.independent", "life.independent_living": "life.independent",
    "pd.independence": "life.independent",

    # Cross-tree
    "cross.ai_growth_operator": "cross.ai_growth_operator",
    "cross.independent_filmmaker": "cross.filmmaker",
    "cross.agentic_business": "cross.agentic_business",
    "cross.unknown_1": "cross.unknown", "cross.unknown_2": "cross.unknown",
}


def main() -> int:
    with open(TREE_PATH, encoding="utf-8") as fh:
        old = json.load(fh)

    if len(old["nodes"]) <= len(structure.NODES):
        print("Tree already looks migrated — nothing to do.")
        return 1

    today = dt.date.today().isoformat()
    new_nodes = structure.build_nodes(old["player"].get("created", today))
    index = {n["id"]: n for n in new_nodes}

    missing = [n["id"] for n in old["nodes"] if n["id"] not in MAP]
    if missing:
        print(f"REFUSING TO MIGRATE — {len(missing)} old node(s) have no mapping:")
        for m in missing:
            print(f"  {m}")
        return 1
    unknown = sorted({v for v in MAP.values()} - set(index))
    if unknown:
        print(f"REFUSING TO MIGRATE — mapping points at nodes that do not exist: {unknown}")
        return 1

    moved_xp = 0.0
    moved_events = 0
    merges: dict[str, list[str]] = {}

    for node in old["nodes"]:
        target = index[MAP[node["id"]]]
        if node.get("xp", 0) > 0:
            merges.setdefault(target["id"], []).append(node["name"])
        target["xp"] = round(target["xp"] + node.get("xp", 0), 1)
        moved_xp += node.get("xp", 0)
        for event in node.get("evidence", []):
            target["evidence"].append(dict(event))
            moved_events += 1
        for kind, amount in node.get("xp_by_type", {}).items():
            target["xp_by_type"][kind] = round(
                target["xp_by_type"].get(kind, 0) + amount, 1)
        if node.get("last_progressed"):
            if not target["last_progressed"] or node["last_progressed"] > target["last_progressed"]:
                target["last_progressed"] = node["last_progressed"]

    for node in new_nodes:
        node["evidence"].sort(key=lambda ev: (ev.get("date", ""), -ev.get("xp", 0)))

    new = {
        "schema_version": old.get("schema_version", 1),
        "player": old["player"],
        "build": old.get("build", {}),
        "attributes": {},
        "trees": [{"id": tid, "name": name, "description": desc, "status": "active"}
                  for tid, name, desc in structure.TREES],
        "nodes": new_nodes,
        "milestones": old.get("milestones", []),
        "quests": old.get("quests", []),
        "interest_signals": old.get("interest_signals", []),
        "history": old.get("history", []),
    }

    before = {n["id"]: n.get("level", 0) for n in old["nodes"]}
    recompute_all(new)

    new["history"].append({
        "date": today,
        "source": "Structural migration: 155 nodes folded into "
                  f"{len(new_nodes)} broader skills. No evidence discarded — "
                  f"{moved_events} events carried across with their dates and reasons. "
                  "Levels shift where several narrow nodes merged into one, because "
                  "the broader skill legitimately holds all of their evidence.",
        "xp_awarded": 0,
        "events": [], "rejected": [],
        "player_level": new["player"]["player_level"],
        "total_xp": new["player"]["total_xp"],
    })

    save_tree(new, TREE_PATH)

    print(f"Migrated {len(old['nodes'])} nodes -> {len(new_nodes)}.")
    print(f"Carried {moved_events} evidence events and {moved_xp:.0f} XP. "
          f"Total XP now {new['player']['total_xp']:.0f} "
          f"(player level {new['player']['player_level']}).")
    print("\nMerged nodes that carried evidence:")
    for nid, sources in sorted(merges.items()):
        if len(sources) > 1:
            node = index[nid]
            olds = ", ".join(sorted(sources))
            print(f"  {node['name']}: Lv {node['level']}  <- {olds}")
    print("\nLevel changes on nodes that kept a one-to-one mapping:")
    for old_id, new_id in MAP.items():
        if sum(1 for v in MAP.values() if v == new_id) == 1:
            was, now = before.get(old_id, 0), index[new_id]["level"]
            if was != now:
                print(f"  {index[new_id]['name']}: {was} -> {now}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
