#!/usr/bin/env python3
"""Personal Skill Tree engine.

Deterministic scoring core for the RPG-style life progression system.

The point of this file is that the *rules* live in code, not in a model's
judgement. Claude decides what evidence exists; this engine decides what that
evidence is worth. That split is what stops levels from inflating.

Commands:
    validate    check the tree file for structural problems
    apply       apply an update file (a day's evidence) to the tree
    render      regenerate PERSONAL_SKILL_TREE.md from the JSON
    dashboard   regenerate the self-contained HTML dashboard
    status      print a short summary
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import os
import sys
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TREE_PATH = os.path.join(ROOT, "data", "PERSONAL_SKILL_TREE.json")
MD_PATH = os.path.join(ROOT, "data", "PERSONAL_SKILL_TREE.md")
DASH_PATH = os.path.join(ROOT, "dashboard", "index.html")

SCHEMA_VERSION = 1

# --------------------------------------------------------------------------
# Progression constants
# --------------------------------------------------------------------------

# Cumulative XP required to *reach* each level. Deliberately brutal at the top:
# 8-10 are meant to be rare, not a reward for persistence in a chat window.
LEVEL_THRESHOLDS = [0, 25, 75, 175, 350, 650, 1100, 1800, 3000, 5200, 9000]

LEVEL_NAMES = [
    "Unknown", "Awareness", "Beginner", "Developing", "Functional", "Competent",
    "Strong", "Advanced", "Expert", "Exceptional", "Mastery",
]

# Evidence kinds, the XP band each may award, and the "class" of the evidence.
# Class drives the hard level cap. XP accumulates; class unlocks.
#   0 talk        1 knowledge      2 practice
#   3 shipped     4 real-world     5 repeated real-world
EVIDENCE = {
    "question":    {"band": (0, 2),      "class": 0, "type": "knowledge"},
    "knowledge":   {"band": (3, 5),      "class": 1, "type": "knowledge"},
    "study":       {"band": (5, 15),     "class": 1, "type": "knowledge"},
    "practice":    {"band": (10, 25),    "class": 2, "type": "experience"},
    "build_small": {"band": (20, 50),    "class": 3, "type": "experience"},
    "project":     {"band": (50, 150),   "class": 3, "type": "experience"},
    "real_world":  {"band": (75, 200),   "class": 4, "type": "mastery"},
    "repeat":      {"band": (100, 300),  "class": 5, "type": "mastery"},
    "milestone":   {"band": (250, 1000), "class": 5, "type": "mastery"},
}

# The ceiling a node's level cannot pass, given the best evidence class on it.
CLASS_LEVEL_CAP = {0: 1, 1: 2, 2: 4, 3: 6, 4: 8, 5: 10}

# Talk is cheap, and priced accordingly: everything in this set shares one
# small global budget per update, across the whole tree.
TALK_KINDS = {"question", "knowledge", "study"}
TALK_DAILY_BUDGET = 60

# Per-node ceiling for a single update, unless the evidence is heavyweight.
NODE_DAILY_CAP = 150
HEAVY_KINDS = {"project", "real_world", "repeat", "milestone"}

# Class 5 (levels 9-10) additionally demands a track record over time, not one
# lucky result. Both conditions must hold.
CLASS5_MIN_EVENTS = 3
CLASS5_MIN_SPAN_DAYS = 180

RUST_DAYS = 45
DORMANT_DAYS = 120

STATUS_BY_LEVEL = {
    0: "Available", 1: "Learning", 2: "Learning", 3: "Practising", 4: "Practising",
    5: "Competent", 6: "Competent", 7: "Advanced", 8: "Advanced",
    9: "Mastered", 10: "Mastered",
}


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def today() -> str:
    return dt.date.today().isoformat()


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value[:10])
    except ValueError:
        return None


def days_since(value: str | None, ref: dt.date | None = None) -> int | None:
    d = parse_date(value)
    if d is None:
        return None
    return ((ref or dt.date.today()) - d).days


def load_tree(path: str = TREE_PATH) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_tree(tree: dict[str, Any], path: str = TREE_PATH) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(tree, fh, indent=2, ensure_ascii=False)
        fh.write("\n")


def node_index(tree: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {n["id"]: n for n in tree["nodes"]}


def level_for_xp(xp: float) -> int:
    level = 0
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i
    return level


def xp_span_for_level(level: int) -> tuple[int, int]:
    """(xp into current level, xp needed for the next one)."""
    if level >= 10:
        return (LEVEL_THRESHOLDS[10], LEVEL_THRESHOLDS[10])
    return (LEVEL_THRESHOLDS[level], LEVEL_THRESHOLDS[level + 1])


def best_class(node: dict[str, Any]) -> int:
    return max((e.get("class", 0) for e in node.get("evidence", [])), default=0)


def cap_for_node(node: dict[str, Any]) -> int:
    """Hard level ceiling implied by the quality of evidence on this node."""
    cls = best_class(node)
    if cls >= 5:
        heavy = [e for e in node.get("evidence", []) if e.get("class", 0) >= 4]
        dates = sorted(d for d in (parse_date(e.get("date")) for e in heavy) if d)
        span = (dates[-1] - dates[0]).days if len(dates) >= 2 else 0
        if len(heavy) < CLASS5_MIN_EVENTS or span < CLASS5_MIN_SPAN_DAYS:
            cls = 4  # a real result, but not yet a track record
    return CLASS_LEVEL_CAP[cls]


def prereqs_met(node: dict[str, Any], idx: dict[str, dict[str, Any]]) -> bool:
    for req in node.get("prerequisites", []):
        if isinstance(req, dict):
            target, need = req.get("node"), req.get("level", 1)
        else:
            target, need = req, 1
        parent = idx.get(target)
        if parent is None or parent.get("level", 0) < need:
            return False
    return True


def confidence_for(node: dict[str, Any]) -> str:
    evidence = node.get("evidence", [])
    if not evidence:
        return "none"
    cls = best_class(node)
    count = len(evidence)
    if cls >= 4 and count >= 3:
        return "high"
    if cls >= 3 or count >= 4:
        return "medium"
    if cls >= 1:
        return "low"
    return "low"


def recompute_node(node: dict[str, Any], idx: dict[str, dict[str, Any]]) -> None:
    """Derive every computed field on a node from its evidence and XP."""
    raw_level = level_for_xp(node.get("xp", 0))
    cap = cap_for_node(node)
    node["level_cap"] = cap
    node["level"] = min(raw_level, cap)
    node["capped"] = raw_level > cap
    node["confidence"] = confidence_for(node)

    types = {e.get("type") for e in node.get("evidence", [])}
    node["knowledge"] = "knowledge" in types or bool(types & {"experience", "mastery"})
    node["experience"] = bool(types & {"experience", "mastery"})
    node["mastery"] = "mastery" in types

    unlocked = prereqs_met(node, idx)
    if not unlocked and node.get("xp", 0) <= 0:
        node["status"] = "Locked"
    else:
        node["status"] = STATUS_BY_LEVEL[node["level"]]

    stale = days_since(node.get("last_progressed"))
    if stale is None or node["level"] < 2:
        node["sharpness"] = "unknown" if stale is None else "current"
    elif stale >= DORMANT_DAYS:
        node["sharpness"] = "dormant"
    elif stale >= RUST_DAYS:
        node["sharpness"] = "rusting"
    else:
        node["sharpness"] = "current"
    node["days_since_progress"] = stale


def player_level(total_xp: float) -> int:
    """Deliberately slow. Doubling your XP does not double your level."""
    level = 0
    while level < 60 and total_xp >= 250 * ((level + 1) ** 2.1):
        level += 1
    return level


ATTRIBUTE_SOURCES = {
    "systems_thinking": ["ai_automation", "technology", "learning"],
    "creativity": ["filmmaking", "art", "content_youtube"],
    "execution": ["*"],
    "technical_ability": ["technology", "ai_automation"],
    "business_ability": ["entrepreneurship", "money"],
    "communication": ["content_youtube", "entrepreneurship", "life_independence"],
    "discipline": ["personal_development", "fitness"],
}


def recompute_attributes(tree: dict[str, Any]) -> None:
    """Attributes are read off the tree, never set by hand.

    Execution is special: it measures the ratio of *doing* XP to total XP, so
    a tree full of reading scores low on it no matter how much XP it holds.
    """
    nodes = tree["nodes"]
    idx_levels = {n["id"]: n.get("level", 0) for n in nodes}
    attrs: dict[str, dict[str, Any]] = {}

    for name, trees in ATTRIBUTE_SOURCES.items():
        if name == "execution":
            doing = sum(n.get("xp_by_type", {}).get("experience", 0)
                        + n.get("xp_by_type", {}).get("mastery", 0) for n in nodes)
            total = sum(n.get("xp", 0) for n in nodes)
            if total <= 0:
                attrs[name] = {"value": 0, "confidence": "none"}
                continue
            ratio = doing / total
            volume = min(1.0, math.log10(1 + doing) / 3.5)
            starting = 10 * ratio * (0.35 + 0.65 * volume)
            # Starting things is not executing. Temper by proven follow-through:
            # a tree full of shipped one-offs and empty consistency nodes is a
            # description of someone who starts well, and should score as one.
            follow = [idx_levels.get(k, 0) for k in
                      ("pd.consistency", "pd.discipline", "fit.consistency", "ent.operations")]
            follow_through = min(1.0, sum(follow) / 16.0)
            attrs[name] = {
                "value": round(starting * (0.4 + 0.6 * follow_through), 1),
                "confidence": "low" if total < 300 else "medium",
                "note": "Tempered by follow-through: consistency and operations nodes "
                        "carry the other 60% of this score.",
            }
            continue

        pool = [n for n in nodes if n.get("tree") in trees and n.get("xp", 0) > 0]
        if not pool:
            attrs[name] = {"value": 0, "confidence": "none"}
            continue
        pool.sort(key=lambda n: n.get("level", 0), reverse=True)
        top = pool[:5]
        # Weighted toward the strongest nodes: breadth alone shouldn't carry it.
        weights = [1.0, 0.7, 0.5, 0.35, 0.25][:len(top)]
        score = sum(n["level"] * w for n, w in zip(top, weights)) / sum(weights)
        attrs[name] = {
            "value": round(min(10.0, score), 1),
            "confidence": "low" if len(pool) < 3 else "medium",
        }

    tree["attributes"] = attrs


def recompute_all(tree: dict[str, Any]) -> None:
    idx = node_index(tree)
    # Two passes: prerequisite status depends on neighbours' recomputed levels.
    for _ in range(2):
        for node in tree["nodes"]:
            recompute_node(node, idx)
    total = sum(n.get("xp", 0) for n in tree["nodes"])
    tree["player"]["total_xp"] = round(total, 1)
    tree["player"]["player_level"] = player_level(total)
    recompute_attributes(tree)


# --------------------------------------------------------------------------
# validate
# --------------------------------------------------------------------------

def cmd_validate(args: argparse.Namespace) -> int:
    tree = load_tree(args.tree)
    idx = node_index(tree)
    problems: list[str] = []

    if tree.get("schema_version") != SCHEMA_VERSION:
        problems.append(f"schema_version is {tree.get('schema_version')}, expected {SCHEMA_VERSION}")

    seen: set[str] = set()
    tree_ids = {t["id"] for t in tree.get("trees", [])}
    for node in tree["nodes"]:
        nid = node.get("id")
        if not nid:
            problems.append("a node is missing an id")
            continue
        if nid in seen:
            problems.append(f"duplicate node id: {nid}")
        seen.add(nid)
        if node.get("tree") not in tree_ids:
            problems.append(f"{nid}: unknown tree '{node.get('tree')}'")
        for req in node.get("prerequisites", []):
            target = req.get("node") if isinstance(req, dict) else req
            if target not in idx:
                problems.append(f"{nid}: prerequisite '{target}' does not exist")
        for nxt in node.get("next_unlock", []):
            if nxt not in idx:
                problems.append(f"{nid}: next_unlock '{nxt}' does not exist")
        if node.get("xp", 0) < 0:
            problems.append(f"{nid}: negative XP")

    # Cycle detection over the prerequisite graph.
    colour: dict[str, int] = {}

    def visit(nid: str, path: list[str]) -> None:
        state = colour.get(nid, 0)
        if state == 1:
            problems.append("prerequisite cycle: " + " -> ".join(path + [nid]))
            return
        if state == 2:
            return
        colour[nid] = 1
        for req in idx[nid].get("prerequisites", []):
            target = req.get("node") if isinstance(req, dict) else req
            if target in idx:
                visit(target, path + [nid])
        colour[nid] = 2

    for nid in idx:
        visit(nid, [])

    if problems:
        print(f"FAIL — {len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"OK — {len(tree['nodes'])} nodes, {len(tree.get('trees', []))} trees, "
          f"{len(tree.get('milestones', []))} milestones, no structural problems.")
    return 0


# --------------------------------------------------------------------------
# apply
# --------------------------------------------------------------------------

def cmd_apply(args: argparse.Namespace) -> int:
    tree = load_tree(args.tree)
    with open(args.update, encoding="utf-8") as fh:
        update = json.load(fh)

    date = update.get("date") or today()
    idx = node_index(tree)
    applied: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    talk_spent = 0
    per_node_spent: dict[str, float] = {}

    # New nodes first, so events in the same update can target them.
    for spec in update.get("new_nodes", []):
        nid = spec.get("id")
        if not nid or nid in idx:
            rejected.append({"node": nid, "reason": "new node missing id or already exists"})
            continue
        node = {
            "id": nid,
            "tree": spec.get("tree", "misc"),
            "name": spec.get("name", nid),
            "tier": spec.get("tier", 1),
            "xp": 0,
            "level": 0,
            "status": "Available",
            "hidden": spec.get("hidden", False),
            "prerequisites": spec.get("prerequisites", []),
            "next_unlock": spec.get("next_unlock", []),
            "unlock_requirement": spec.get("unlock_requirement", ""),
            "evidence": [],
            "xp_by_type": {},
            "last_progressed": None,
            "created": date,
            "note": spec.get("note", ""),
        }
        tree["nodes"].append(node)
        idx[nid] = node
        applied.append({"node": nid, "xp": 0, "reason": "node created"})

    for event in update.get("events", []):
        nid = event.get("node")
        kind = event.get("kind")
        node = idx.get(nid)

        if node is None:
            rejected.append({"node": nid, "reason": "unknown node"})
            continue
        if kind not in EVIDENCE:
            rejected.append({"node": nid, "reason": f"unknown evidence kind '{kind}'"})
            continue
        reason = (event.get("reason") or "").strip()
        if not reason:
            rejected.append({"node": nid, "reason": "evidence with no stated reason is not accepted"})
            continue

        spec = EVIDENCE[kind]
        lo, hi = spec["band"]
        requested = event.get("xp", lo)
        xp = max(lo, min(hi, float(requested)))
        note = []
        if float(requested) != xp:
            note.append(f"clamped from {requested} to band {lo}-{hi}")

        # A milestone must name the event that actually happened.
        if kind == "milestone" and not event.get("occurred"):
            rejected.append({"node": nid, "reason": "milestone events require occurred: true"})
            continue

        # Talk budget, shared across the whole update.
        if kind in TALK_KINDS:
            room = TALK_DAILY_BUDGET - talk_spent
            if room <= 0:
                rejected.append({"node": nid, "reason": "discussion XP budget for this update is exhausted"})
                continue
            if xp > room:
                note.append(f"trimmed to remaining discussion budget ({room})")
                xp = room
            talk_spent += xp

        # Per-node ceiling for ordinary evidence. Heavyweight evidence is
        # exempt and, importantly, does not consume the budget either — a
        # finished project must not crowd out the practice that surrounds it.
        if kind not in HEAVY_KINDS:
            spent = per_node_spent.get(nid, 0)
            room = NODE_DAILY_CAP - spent
            if room <= 0:
                rejected.append({"node": nid, "reason": "per-node XP cap for this update reached"})
                continue
            if xp > room:
                note.append(f"trimmed to node cap (+{room})")
                xp = room
            per_node_spent[nid] = spent + xp

        before = node.get("level", 0)
        node["xp"] = round(node.get("xp", 0) + xp, 1)
        node.setdefault("evidence", []).append({
            "date": date,
            "kind": kind,
            "class": spec["class"],
            "type": spec["type"],
            "xp": xp,
            "reason": reason,
        })
        by_type = node.setdefault("xp_by_type", {})
        by_type[spec["type"]] = round(by_type.get(spec["type"], 0) + xp, 1)
        if spec["class"] >= 2:
            node["last_progressed"] = date
        elif not node.get("last_progressed"):
            node["last_progressed"] = date

        recompute_node(node, idx)
        applied.append({
            "node": nid, "name": node["name"], "kind": kind, "xp": xp,
            "reason": reason, "level_before": before, "level_after": node["level"],
            "capped": node.get("capped", False),
            "notes": "; ".join(note),
        })

    for signal in update.get("interest_signals", []):
        topic = signal.get("topic")
        if not topic:
            continue
        existing = next((s for s in tree.setdefault("interest_signals", [])
                         if s["topic"].lower() == topic.lower()), None)
        if existing:
            existing["mentions"] = existing.get("mentions", 0) + int(signal.get("weight", 1))
            existing["last_seen"] = date
            existing.setdefault("notes", []).append(signal.get("note", ""))
        else:
            tree["interest_signals"].append({
                "topic": topic,
                "mentions": int(signal.get("weight", 1)),
                "first_seen": date,
                "last_seen": date,
                "notes": [signal.get("note", "")],
                "stage": "signal",
            })

    for signal in tree.get("interest_signals", []):
        count = signal.get("mentions", 0)
        signal["stage"] = "branch candidate" if count >= 4 else "emerging" if count >= 2 else "signal"

    for claim in update.get("milestones_claimed", []):
        mid = claim.get("id")
        milestone = next((m for m in tree.get("milestones", []) if m["id"] == mid), None)
        if milestone is None:
            rejected.append({"node": mid, "reason": "unknown milestone"})
            continue
        if not claim.get("occurred"):
            rejected.append({"node": mid, "reason": "milestone claimed without occurred: true"})
            continue
        if milestone.get("unlocked"):
            continue
        milestone["unlocked"] = True
        milestone["date"] = date
        milestone["evidence"] = claim.get("reason", "")
        applied.append({"node": mid, "kind": "milestone", "xp": 0,
                        "reason": f"MILESTONE UNLOCKED — {milestone['name']}"})

    if "quests" in update:
        tree["quests"] = update["quests"]

    # A build is a read on sustained behaviour, so it is set explicitly and
    # rarely — never derived automatically from a good week.
    if "build" in update:
        tree.setdefault("build", {}).update(update["build"])

    recompute_all(tree)

    entry = {
        "date": date,
        "source": update.get("source", ""),
        "xp_awarded": round(sum(a.get("xp", 0) for a in applied), 1),
        "events": applied,
        "rejected": rejected,
        "player_level": tree["player"]["player_level"],
        "total_xp": tree["player"]["total_xp"],
    }
    tree.setdefault("history", []).append(entry)
    tree["player"]["last_update"] = date

    if args.dry_run:
        print(json.dumps(entry, indent=2))
        print("\n(dry run — nothing written)")
        return 0

    save_tree(tree, args.tree)
    print(f"Applied {len(applied)} event(s), rejected {len(rejected)}, "
          f"+{entry['xp_awarded']} XP. Player level {tree['player']['player_level']}.")
    for r in rejected:
        print(f"  rejected: {r['node']} — {r['reason']}")
    return 0


# --------------------------------------------------------------------------
# render (markdown)
# --------------------------------------------------------------------------

def bar(value: float, maximum: float, width: int = 10) -> str:
    if maximum <= 0:
        return "░" * width
    filled = int(round(width * max(0.0, min(1.0, value / maximum))))
    return "█" * filled + "░" * (width - filled)


def cmd_render(args: argparse.Namespace) -> int:
    tree = load_tree(args.tree)
    recompute_all(tree)
    player = tree["player"]
    idx = node_index(tree)
    out: list[str] = []
    w = out.append

    w(f"# {player['name'].upper()} — PERSONAL SKILL TREE")
    w("")
    w(f"*Last updated: {player.get('last_update') or 'never'} · "
      f"generated by `scripts/skilltree.py render` — do not hand-edit.*")
    w("")

    w("## Player")
    w("")
    w(f"- **Player level:** {player['player_level']}")
    w(f"- **Total XP:** {player['total_xp']:.0f}")
    w(f"- **Nodes with evidence:** {sum(1 for n in tree['nodes'] if n.get('xp', 0) > 0)} "
      f"of {len(tree['nodes'])}")
    w("")

    build = tree.get("build", {})
    w("## Current build")
    w("")
    if build.get("primary_class"):
        w(f"- **Primary class:** {build['primary_class']}")
        w(f"- **Secondary class:** {build.get('secondary_class') or '—'}")
        w(f"- **Creative class:** {build.get('creative_class') or '—'}")
        w(f"- **Confidence:** {build.get('confidence', 'none')}")
    else:
        w("*Undetermined. A build is inferred from sustained behaviour, not "
          "declared upfront — it stays empty until the evidence names it.*")
    w("")

    w("## Core attributes")
    w("")
    w("| Attribute | | Value | Confidence |")
    w("|---|---|---|---|")
    for name, data in tree.get("attributes", {}).items():
        label = name.replace("_", " ").title()
        w(f"| {label} | `{bar(data['value'], 10)}` | {data['value']}/10 | {data['confidence']} |")
    w("")

    w("## Skill trees")
    w("")
    for branch in tree["trees"]:
        nodes = [n for n in tree["nodes"] if n.get("tree") == branch["id"]]
        visible = [n for n in nodes if not n.get("hidden")]
        hidden = [n for n in nodes if n.get("hidden")]
        active = [n for n in visible if n.get("xp", 0) > 0]
        w(f"### {branch['name']}")
        w("")
        if branch.get("description"):
            w(f"*{branch['description']}*")
            w("")
        if not active:
            w(f"No evidence recorded yet — {len(visible)} nodes awaiting assessment.")
            w("")
        else:
            w("| Skill | Level | Status | XP | Confidence | Note |")
            w("|---|---|---|---|---|---|")
            for node in sorted(active, key=lambda n: (-n.get("level", 0), n["name"])):
                lo, hi = xp_span_for_level(node["level"])
                xp_txt = f"{node['xp']:.0f}/{hi}" if node["level"] < 10 else f"{node['xp']:.0f}"
                flags = []
                if node.get("capped"):
                    flags.append(f"capped at {node['level_cap']} by evidence class")
                if node.get("sharpness") == "rusting":
                    flags.append(f"⚠ rusting ({node['days_since_progress']}d)")
                if node.get("sharpness") == "dormant":
                    flags.append(f"⚠ dormant ({node['days_since_progress']}d)")
                w(f"| {node['name']} | {node['level']} — {LEVEL_NAMES[node['level']]} | "
                  f"{node['status']} | {xp_txt} | {node['confidence']} | {'; '.join(flags)} |")
            w("")
            dormant = [n for n in visible if n.get("xp", 0) == 0]
            if dormant:
                w(f"<sub>{len(dormant)} further nodes in this tree hold no evidence yet.</sub>")
                w("")
        if hidden:
            w(f"<sub>??? — {len(hidden)} hidden node(s) beyond this branch.</sub>")
            w("")

    w("## Nearest unlocks")
    w("")
    near = nearest_unlocks(tree, idx)
    if near:
        for item in near:
            state = "ready now — prerequisites met, no evidence yet" if item["ready"] \
                else f"{item['pct']}% of prerequisites met"
            w(f"- **{item['name']}** — {state}")
            if item["missing"]:
                w(f"  - Missing: {'; '.join(item['missing'])}")
            if item["requirement"]:
                w(f"  - Requirement: {item['requirement']}")
    else:
        w("*Nothing is close yet — the tree needs its first evidence.*")
    w("")

    w("## Current quests")
    w("")
    quests = tree.get("quests", [])
    if quests:
        for quest in quests:
            stars = "★" * quest.get("difficulty", 3) + "☆" * (5 - quest.get("difficulty", 3))
            w(f"### {quest['name']}")
            w("")
            w(f"{quest.get('description', '')}")
            w("")
            w(f"- **Reward:** {quest.get('reward', '')}")
            w(f"- **Unlocks:** {quest.get('unlocks', '—')}")
            w(f"- **Difficulty:** {stars}")
            w(f"- **Proof required:** {quest.get('proof', '')}")
            w("")
    else:
        w("*No quests set.*")
    w("")

    w("## Milestones")
    w("")
    for milestone in tree.get("milestones", []):
        mark = "✅" if milestone.get("unlocked") else "🔒"
        date = f" — {milestone['date']}" if milestone.get("unlocked") else ""
        w(f"- {mark} **{milestone['name']}**{date} — <sub>{milestone.get('requirement', '')}</sub>")
    w("")

    signals = tree.get("interest_signals", [])
    if signals:
        w("## Interest signals")
        w("")
        w("| Topic | Mentions | Stage | Last seen |")
        w("|---|---|---|---|")
        for s in sorted(signals, key=lambda s: -s.get("mentions", 0)):
            w(f"| {s['topic']} | {s.get('mentions', 0)} | {s.get('stage', '')} | {s.get('last_seen', '')} |")
        w("")

    history = tree.get("history", [])
    if history:
        w("## Recent updates")
        w("")
        for entry in history[-5:][::-1]:
            w(f"### {entry['date']} — +{entry['xp_awarded']:.0f} XP")
            w("")
            for event in entry["events"]:
                if event.get("xp"):
                    change = ""
                    if event.get("level_after", 0) > event.get("level_before", 0):
                        change = f" *(level {event['level_before']} → {event['level_after']})*"
                    w(f"- **{event.get('name', event['node'])}** +{event['xp']:.0f} XP{change} — {event['reason']}")
                else:
                    w(f"- {event['reason']}")
            w("")

    with open(args.md or MD_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    if not args.dry_run:
        save_tree(tree, args.tree)
    print(f"Wrote {args.md or MD_PATH}")
    return 0


def nearest_unlocks(tree: dict[str, Any], idx: dict[str, dict[str, Any]], limit: int = 7) -> list[dict[str, Any]]:
    results = []
    for node in tree["nodes"]:
        if node.get("hidden") or node.get("xp", 0) > 0:
            continue
        reqs = node.get("prerequisites", [])
        if not reqs:
            continue
        met, missing = 0, []
        for req in reqs:
            target, need = (req.get("node"), req.get("level", 1)) if isinstance(req, dict) else (req, 1)
            parent = idx.get(target)
            if parent and parent.get("level", 0) >= need:
                met += 1
            elif parent:
                missing.append(f"{parent['name']} to level {need} (now {parent.get('level', 0)})")
        pct = int(round(100 * met / len(reqs)))
        if pct > 0:
            results.append({"name": node["name"], "pct": pct, "missing": missing,
                            "ready": pct == 100, "tier": node.get("tier", 1),
                            "requirement": node.get("unlock_requirement", "")})
    # Fully-unlocked-but-untouched nodes first: those are startable today.
    results.sort(key=lambda r: (-r["pct"], r["tier"]))
    return results[:limit]


# --------------------------------------------------------------------------
# dashboard
# --------------------------------------------------------------------------

DASH_CSS = """
:root{--bg:#f6f7f9;--panel:#fff;--ink:#14161a;--muted:#5f6773;--line:#e2e5ea;
--accent:#3b6ef5;--gold:#b8860b;--lock:#aab1bb;--rust:#b45309;--track:#e8ebf0}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#0f1115;--panel:#171a20;
--ink:#e8eaee;--muted:#98a1af;--line:#262b33;--accent:#7aa2ff;--gold:#e3b341;--lock:#4c545f;
--rust:#e0a458;--track:#232830}}
:root[data-theme=dark]{--bg:#0f1115;--panel:#171a20;--ink:#e8eaee;--muted:#98a1af;
--line:#262b33;--accent:#7aa2ff;--gold:#e3b341;--lock:#4c545f;--rust:#e0a458;--track:#232830}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;padding:32px 20px 80px}
.wrap{max-width:1120px;margin:0 auto}
h1{font-size:26px;letter-spacing:.08em;margin:0 0 4px}
.sub{color:var(--muted);font-size:13px;margin-bottom:28px}
.grid{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));margin-bottom:28px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
.card h2{font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0 0 12px}
.big{font-size:34px;font-weight:650;line-height:1}
.attr{display:grid;grid-template-columns:1fr 90px 34px;gap:8px;align-items:center;
font-size:13px;margin-bottom:7px}
.track{height:7px;background:var(--track);border-radius:99px;overflow:hidden}
.fill{height:100%;background:var(--accent);border-radius:99px;transition:width .9s cubic-bezier(.2,.8,.2,1)}
.branch{background:var(--panel);border:1px solid var(--line);border-radius:12px;
padding:16px;margin-bottom:14px}
.branch>h3{margin:0 0 2px;font-size:15px}
.branch .desc{color:var(--muted);font-size:12.5px;margin-bottom:12px}
.node{border-top:1px solid var(--line);padding:10px 0;display:grid;
grid-template-columns:1fr 130px 66px;gap:10px;align-items:center}
.node:first-of-type{border-top:0}
.node .nm{font-weight:550}
.node .meta{color:var(--muted);font-size:12px}
.node.locked .nm,.node.locked .meta{color:var(--lock)}
.node .lv{text-align:right;font-variant-numeric:tabular-nums;font-size:13px;color:var(--muted)}
.empty{color:var(--muted);font-size:13px;font-style:italic}
.tag{display:inline-block;font-size:10.5px;letter-spacing:.05em;text-transform:uppercase;
border:1px solid var(--line);border-radius:99px;padding:1px 7px;margin-left:6px;color:var(--muted)}
.tag.rust{color:var(--rust);border-color:var(--rust)}
.tag.cap{color:var(--gold);border-color:var(--gold)}
.ms{display:flex;justify-content:space-between;gap:12px;padding:8px 0;
border-top:1px solid var(--line);font-size:13.5px}
.ms:first-of-type{border-top:0}
.ms.locked{color:var(--lock)}
.quest{border-top:1px solid var(--line);padding:12px 0}
.quest:first-of-type{border-top:0}
.quest .qn{font-weight:600;margin-bottom:3px}
.quest .qd{color:var(--muted);font-size:13px}
.stars{color:var(--gold);font-size:12px;letter-spacing:2px}
.cols{display:grid;gap:16px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
"""


def cmd_dashboard(args: argparse.Namespace) -> int:
    tree = load_tree(args.tree)
    recompute_all(tree)
    player = tree["player"]
    idx = node_index(tree)
    e = html.escape
    p: list[str] = []
    w = p.append

    w(f"<title>{e(player['name'])} — Personal Skill Tree</title>")
    w(f"<style>{DASH_CSS}</style>")
    w('<div class="wrap">')
    w(f"<h1>{e(player['name'].upper())} — PERSONAL SKILL TREE</h1>")
    w(f'<div class="sub">Last updated {e(player.get("last_update") or "never")} · '
      f'{sum(1 for n in tree["nodes"] if n.get("xp",0)>0)} of {len(tree["nodes"])} nodes carry evidence</div>')

    w('<div class="grid">')
    w(f'<div class="card"><h2>Player level</h2><div class="big">{player["player_level"]}</div></div>')
    w(f'<div class="card"><h2>Total XP</h2><div class="big">{player["total_xp"]:.0f}</div></div>')
    build = tree.get("build", {})
    build_txt = e(build.get("primary_class") or "Undetermined")
    w(f'<div class="card"><h2>Primary class</h2><div class="big" style="font-size:20px">{build_txt}</div>'
      f'<div class="meta" style="color:var(--muted);font-size:12px;margin-top:6px">'
      f'confidence: {e(build.get("confidence","none"))}</div></div>')
    unlocked = sum(1 for m in tree.get("milestones", []) if m.get("unlocked"))
    w(f'<div class="card"><h2>Milestones</h2><div class="big">{unlocked}'
      f'<span style="font-size:16px;color:var(--muted)">/{len(tree.get("milestones", []))}</span></div></div>')
    w("</div>")

    w('<div class="card" style="margin-bottom:28px"><h2>Core attributes</h2>')
    for name, data in tree.get("attributes", {}).items():
        pct = 10 * data["value"]
        w(f'<div class="attr"><span>{e(name.replace("_"," ").title())}</span>'
          f'<span class="track"><span class="fill" style="width:{pct}%"></span></span>'
          f'<span style="text-align:right;color:var(--muted);font-size:12px">{data["value"]}</span></div>')
    w("</div>")

    for branch in tree["trees"]:
        nodes = [n for n in tree["nodes"] if n.get("tree") == branch["id"]]
        visible = sorted([n for n in nodes if not n.get("hidden")],
                         key=lambda n: (n.get("tier", 1), n["name"]))
        hidden = [n for n in nodes if n.get("hidden")]
        w('<div class="branch">')
        w(f"<h3>{e(branch['name'])}</h3>")
        if branch.get("description"):
            w(f'<div class="desc">{e(branch["description"])}</div>')
        for node in visible:
            locked = node.get("status") == "Locked"
            tags = ""
            if node.get("capped"):
                tags += f'<span class="tag cap">cap {node["level_cap"]}</span>'
            if node.get("sharpness") in ("rusting", "dormant"):
                tags += f'<span class="tag rust">{node["sharpness"]}</span>'
            lo, hi = xp_span_for_level(node["level"])
            pct = 0 if hi <= lo else 100 * (node["xp"] - lo) / (hi - lo)
            pct = max(0, min(100, pct))
            w(f'<div class="node{" locked" if locked else ""}">')
            w(f'<div><div class="nm">{e(node["name"])}{tags}</div>'
              f'<div class="meta">{e(node["status"])} · {e(LEVEL_NAMES[node["level"]])} · '
              f'confidence {e(node.get("confidence","none"))}</div></div>')
            w(f'<span class="track"><span class="fill" style="width:{pct:.0f}%"></span></span>')
            w(f'<div class="lv">Lv {node["level"]}</div>')
            w("</div>")
        if hidden:
            w(f'<div class="node locked"><div><div class="nm">???</div>'
              f'<div class="meta">{len(hidden)} node(s) hidden until prerequisites are met</div></div>'
              f'<span class="track"></span><div class="lv">—</div></div>')
        w("</div>")

    w('<div class="cols">')
    w('<div class="card"><h2>Current quests</h2>')
    for quest in tree.get("quests", []) or []:
        stars = "★" * quest.get("difficulty", 3) + "☆" * (5 - quest.get("difficulty", 3))
        w(f'<div class="quest"><div class="qn">{e(quest["name"])}</div>'
          f'<div class="qd">{e(quest.get("description",""))}</div>'
          f'<div class="qd" style="margin-top:6px">Reward: {e(quest.get("reward",""))}</div>'
          f'<div class="qd">Proof: {e(quest.get("proof",""))}</div>'
          f'<div class="stars">{stars}</div></div>')
    if not tree.get("quests"):
        w('<div class="empty">No quests set.</div>')
    w("</div>")

    w('<div class="card"><h2>Milestones</h2>')
    for milestone in tree.get("milestones", []):
        cls = "" if milestone.get("unlocked") else " locked"
        mark = "✅" if milestone.get("unlocked") else "🔒"
        right = milestone.get("date", "") if milestone.get("unlocked") else "locked"
        w(f'<div class="ms{cls}"><span>{mark} {e(milestone["name"])}</span>'
          f'<span style="color:var(--muted);font-size:12px;white-space:nowrap">{e(right)}</span></div>')
    w("</div>")
    w("</div>")

    near = nearest_unlocks(tree, idx)
    if near:
        w('<div class="card" style="margin-top:16px"><h2>Nearest unlocks</h2>')
        for item in near:
            w(f'<div class="attr"><span>{e(item["name"])}</span>'
              f'<span class="track"><span class="fill" style="width:{item["pct"]}%"></span></span>'
              f'<span style="text-align:right;color:var(--muted);font-size:12px">{item["pct"]}%</span></div>')
            if item["missing"]:
                w(f'<div class="empty" style="margin:-2px 0 10px">Missing: {e("; ".join(item["missing"]))}</div>')
        w("</div>")

    w("</div>")

    path = args.out or DASH_PATH
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(p))
    print(f"Wrote {path}")
    return 0


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    tree = load_tree(args.tree)
    recompute_all(tree)
    player = tree["player"]
    active = [n for n in tree["nodes"] if n.get("xp", 0) > 0]
    print(f"{player['name']} — player level {player['player_level']}, {player['total_xp']:.0f} XP")
    print(f"Last update: {player.get('last_update') or 'never'}")
    print(f"Nodes with evidence: {len(active)}/{len(tree['nodes'])}")
    rusting = [n for n in active if n.get("sharpness") in ("rusting", "dormant")]
    if rusting:
        print("\nRusting:")
        for n in sorted(rusting, key=lambda n: -(n.get("days_since_progress") or 0)):
            print(f"  {n['name']} (Lv {n['level']}) — {n['days_since_progress']}d since practice")
    if active:
        print("\nStrongest:")
        for n in sorted(active, key=lambda n: -n["level"])[:8]:
            flag = f"  [capped at {n['level_cap']}]" if n.get("capped") else ""
            print(f"  {n['name']}: Lv {n['level']} ({n['xp']:.0f} XP, {n['confidence']} confidence){flag}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Personal Skill Tree engine")
    parser.add_argument("--tree", default=TREE_PATH, help="path to PERSONAL_SKILL_TREE.json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate").set_defaults(func=cmd_validate)

    apply_p = sub.add_parser("apply")
    apply_p.add_argument("update", help="path to an update JSON file")
    apply_p.add_argument("--dry-run", action="store_true")
    apply_p.set_defaults(func=cmd_apply)

    render_p = sub.add_parser("render")
    render_p.add_argument("--md", default=None)
    render_p.add_argument("--dry-run", action="store_true")
    render_p.set_defaults(func=cmd_render)

    dash_p = sub.add_parser("dashboard")
    dash_p.add_argument("--out", default=None)
    dash_p.set_defaults(func=cmd_dashboard)

    sub.add_parser("status").set_defaults(func=cmd_status)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
