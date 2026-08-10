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
    """Persist the tree, minus anything derived from today's date.

    `days_since_progress` changes every single day on every node, which would
    make the file churn daily and bury real evidence in noise. It is computed
    for display and dropped on the way to disk. `sharpness` is kept, because it
    only moves when a node crosses the 45- or 120-day threshold — so a diff on
    this file always means something actually happened.
    """
    snapshot = json.loads(json.dumps(tree))
    for node in snapshot.get("nodes", []):
        node.pop("days_since_progress", None)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(snapshot, fh, indent=2, ensure_ascii=False)
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
TREE_CSS = """
/* A constellation reads on a dark ground, so this view commits to one
   visual world rather than shipping a washed-out light variant. Every
   colour is painted explicitly so the page holds on any host background.
   Palette is Brajan's AIGO brand: near-black, cream, signal red, with
   ochre reserved for evidence ceilings so it never fights the accent. */
:root{
  --void:#0E0D0C; --void-2:#151311;
  --cream:#F7F6F2; --muted:#A9A296; --faint:#7C7568;
  --accent:#FF5C4C; --accent-dim:#B03A2C;
  --ochre:#D9A05B;
  --edge:#403B32; --edge-lit:#FF6A5A;
  --node:#1E1B17; --node-line:#4E483D;
  --panel:#131110;
}
*{box-sizing:border-box}
html,body{height:100%}
body{
  margin:0;background:var(--void);color:var(--cream);overflow:hidden;
  font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
}
.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace}
#stage{position:fixed;inset:0;background:
  radial-gradient(ellipse at 50% 45%,#1A1714 0%,var(--void) 62%,#080807 100%);
  cursor:grab;touch-action:none}
#stage.drag{cursor:grabbing}
svg{width:100%;height:100%;display:block}

.edge{stroke:var(--edge);stroke-width:2.6;fill:none}
.edge.cross{stroke-dasharray:8 9;stroke:#3A352C}
.edge.done{stroke:var(--accent-dim);stroke-width:3.4}
.edge.lit{stroke:var(--edge-lit);stroke-width:4.5}
/* With something selected, everything unrelated recedes so the one
   chain you are reading is the only thing lit. */
#cam.focus .edge:not(.lit){opacity:.1}

.node{cursor:pointer}
.node .disc{fill:var(--node);stroke:var(--node-line);stroke-width:3}
.node.avail .disc{stroke:var(--faint)}
.node.has .disc{fill:#2A1712;stroke:var(--accent);stroke-width:3.5}
.node.hidden .disc{stroke-dasharray:4 5;stroke:#2E2B25;fill:#111}
.node .ring{fill:none;stroke:var(--accent);stroke-width:6;stroke-linecap:butt;
  transform:rotate(-90deg);transform-box:fill-box;transform-origin:center}
.node .cap{fill:none;stroke:var(--ochre);stroke-width:3;opacity:.85;
  transform:rotate(-90deg);transform-box:fill-box;transform-origin:center}
.node .lv{fill:var(--cream);font-size:30px;font-weight:700;text-anchor:middle;
  dominant-baseline:central;pointer-events:none}
.node.idle .lv{fill:var(--faint)}
.node .lbl{fill:var(--faint);font-size:21px;opacity:.62;transition:opacity .15s;text-anchor:middle;pointer-events:none;
  paint-order:stroke;stroke:var(--void);stroke-width:7px;stroke-linejoin:round}
.node.has .lbl{fill:#E4DDD0;font-weight:600}
.node.has .lbl{opacity:1}
.node:hover .lbl,.node.sel .lbl,.node:focus .lbl{fill:var(--cream);opacity:1}
.node.sel .disc{stroke:var(--accent);stroke-width:3}
.node.dim{opacity:.13}
.node .halo{fill:var(--accent);opacity:0;transition:opacity .18s}
.node.sel .halo{opacity:.13}
.node:focus{outline:none}
.node:focus .disc{stroke:var(--cream)}
.rust{fill:var(--ochre)}

.branch-label{fill:#9A9182;font-size:30px;letter-spacing:.2em;text-anchor:middle;
  text-transform:uppercase;pointer-events:none;font-weight:600}

/* ---- detail panel ---- */
#panel{position:fixed;top:0;right:0;bottom:0;width:min(400px,92vw);background:var(--panel);
  border-left:1px solid #26231E;transform:translateX(101%);transition:transform .26s cubic-bezier(.2,.8,.2,1);
  overflow-y:auto;padding:24px 24px 60px;display:flex;flex-direction:column;gap:16px}
#panel.open{transform:none}
#panel .eyebrow{font-size:10px;letter-spacing:.18em;text-transform:uppercase;color:var(--accent)}
#panel h2{margin:0;font-size:23px;font-weight:750;letter-spacing:-.02em;line-height:1.15}
#panel .state{display:flex;flex-wrap:wrap;gap:7px;align-items:center}
#close{position:absolute;top:14px;right:14px;background:none;border:1px solid #2E2A24;
  color:var(--muted);width:30px;height:30px;cursor:pointer;font-size:15px;line-height:1}
#close:hover{color:var(--cream);border-color:var(--faint)}
.pill{font-size:10px;letter-spacing:.1em;text-transform:uppercase;padding:3px 8px;
  border:1px solid currentColor;color:var(--muted);white-space:nowrap}
.pill.on{color:var(--accent)}
.pill.warn{color:var(--ochre)}
.segs{display:flex;gap:2px;height:10px}
.segs span{flex:1;background:#24211C}
.segs span.on{background:var(--accent)}
.segs span.blocked{background:repeating-linear-gradient(135deg,#3A362E 0 2px,transparent 2px 4px)}
.xp{font-size:12px;color:var(--muted)}
#panel h3{margin:0;font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--faint);
  border-bottom:1px solid #221F1A;padding-bottom:6px}
#panel section{display:flex;flex-direction:column;gap:9px}
#panel p{margin:0;font-size:13.5px;color:#B8B1A5}
.req{display:flex;gap:9px;align-items:baseline;font-size:13px;cursor:pointer;
  background:none;border:0;color:inherit;padding:0;text-align:left;width:100%;font-family:inherit}
.req:hover .rn{color:var(--accent)}
.req .mk{width:13px;flex:none;font-size:12px}
.req .mk.ok{color:var(--accent)}
.req .mk.no{color:var(--faint)}
.req .rn{color:#C9C2B6}
.req .rs{color:var(--faint);font-size:11.5px;margin-left:auto;white-space:nowrap;padding-left:8px}
.ev{border-left:2px solid #2A2620;padding:2px 0 2px 11px;display:flex;flex-direction:column;gap:3px}
.ev .top{display:flex;gap:8px;font-size:10.5px;color:var(--faint);letter-spacing:.06em;
  text-transform:uppercase}
.ev .top b{color:var(--ochre);font-weight:600}
.ev p{font-size:12.5px;color:#A8A196}
.none{font-size:13px;color:var(--faint);font-style:italic}

/* ---- controls ---- */
#zoom{position:fixed;left:18px;bottom:18px;display:flex;flex-direction:column;gap:1px;background:#26231E}
#zoom button{width:34px;height:34px;background:var(--void-2);border:0;color:var(--muted);
  font-size:16px;cursor:pointer;font-family:inherit}
#zoom button:hover{color:var(--cream);background:#221F1B}
#legend{position:fixed;left:64px;bottom:18px;display:flex;gap:14px;flex-wrap:wrap;
  font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--faint);
  align-items:center;max-width:min(560px,60vw)}
#legend i{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;
  vertical-align:-1px;border:1.5px solid var(--node-line);background:var(--node)}
#legend i.has{border-color:var(--accent-dim);background:#211512}
#legend i.av{border-color:var(--faint)}
#legend i.cap{border-color:var(--ochre);background:none}
#hint{position:fixed;top:18px;left:18px;font-size:11px;letter-spacing:.1em;
  text-transform:uppercase;color:var(--faint)}
@media (max-width:640px){#legend{display:none}}
"""

TREE_JS = r"""
const S=document.getElementById('stage'),SVG=document.getElementById('svg'),
      G=document.getElementById('cam'),P=document.getElementById('panel');
let vb={x:VB0.x,y:VB0.y,w:VB0.w,h:VB0.h};
function apply(){SVG.setAttribute('viewBox',`${vb.x} ${vb.y} ${vb.w} ${vb.h}`)}
function fit(){
  const r=S.getBoundingClientRect(), a=r.width/r.height, size=VB0.w;
  if(a>=1){vb.h=size;vb.w=size*a}else{vb.w=size;vb.h=size/a}
  vb.x=VB0.cx-vb.w/2; vb.y=VB0.cy-vb.h/2; apply();
}
fit(); addEventListener('resize',fit);

/* pan */
let dragging=false,sx=0,sy=0,moved=0;
S.addEventListener('pointerdown',e=>{dragging=true;moved=0;sx=e.clientX;sy=e.clientY;
  S.classList.add('drag');S.setPointerCapture(e.pointerId)});
S.addEventListener('pointermove',e=>{if(!dragging)return;
  const r=S.getBoundingClientRect(),k=vb.w/r.width;
  const dx=e.clientX-sx,dy=e.clientY-sy;moved+=Math.abs(dx)+Math.abs(dy);
  vb.x-=dx*k;vb.y-=dy*k;sx=e.clientX;sy=e.clientY;apply()});
addEventListener('pointerup',()=>{dragging=false;S.classList.remove('drag')});

/* zoom */
function zoom(f,cx,cy){
  const nw=Math.max(320,Math.min(7000,vb.w*f));f=nw/vb.w;
  vb.x=cx-(cx-vb.x)*f; vb.y=cy-(cy-vb.y)*f; vb.w=nw; vb.h*=f; apply();
}
S.addEventListener('wheel',e=>{e.preventDefault();
  const r=S.getBoundingClientRect(),k=vb.w/r.width;
  zoom(e.deltaY>0?1.12:0.89, vb.x+(e.clientX-r.left)*k, vb.y+(e.clientY-r.top)*k);
},{passive:false});
document.getElementById('zin').onclick=()=>zoom(0.8,vb.x+vb.w/2,vb.y+vb.h/2);
document.getElementById('zout').onclick=()=>zoom(1.25,vb.x+vb.w/2,vb.y+vb.h/2);
document.getElementById('zfit').onclick=()=>{fit();deselect()};

/* selection */
const els={},edges=[...document.querySelectorAll('.edge')];
document.querySelectorAll('.node').forEach(n=>els[n.dataset.id]=n);
let cur=null;
function deselect(){cur=null;P.classList.remove('open');G.classList.remove('focus');
  Object.values(els).forEach(n=>n.classList.remove('sel','dim'));
  edges.forEach(e=>e.classList.remove('lit'))}
function seg(level,cap){let h='';for(let i=1;i<=10;i++){
  h+= i<=level?'<span class="on"></span>': i>cap?'<span class="blocked"></span>':'<span></span>'}
  return `<div class="segs">${h}</div>`}
function reqRow(id,need){const n=DATA[id];if(!n)return'';
  const ok=n.level>=need;
  return `<button class="req" data-go="${id}"><span class="mk ${ok?'ok':'no'}">${ok?'✓':'○'}</span>`+
    `<span class="rn">${n.name}</span><span class="rs">${ok?`Lv ${n.level}`:`needs Lv ${need}, at ${n.level}`}</span></button>`}
function show(id){
  const n=DATA[id];if(!n)return;
  cur=id;
  Object.values(els).forEach(e=>e.classList.remove('sel'));
  const near=new Set([id,...n.prereq.map(p=>p[0]),...n.unlocks]);
  Object.values(els).forEach(e=>e.classList.toggle('dim',!near.has(e.dataset.id)));
  edges.forEach(e=>e.classList.toggle('lit',e.dataset.a===id||e.dataset.b===id));
  els[id].classList.add('sel');G.classList.add('focus');
  const pills=[`<span class="pill ${n.xp>0?'on':''}">${n.status}</span>`,
    `<span class="pill">${n.levelName}</span>`,
    n.cap<10?`<span class="pill warn">ceiling ${n.cap}</span>`:'',
    n.rust?`<span class="pill warn">${n.rust}</span>`:'',
    `<span class="pill">confidence ${n.conf}</span>`].join('');
  P.innerHTML=`<button id="close" aria-label="Close">✕</button>
    <div class="eyebrow">${n.treeName}</div>
    <h2>${n.name}</h2>
    <div class="state">${pills}</div>
    ${seg(n.level,n.cap)}
    <div class="xp mono">Level ${n.level} · ${n.xp} XP${n.next?` · ${n.next} XP to level ${n.level+1}`:''}</div>
    ${n.cap<10?`<p><b style="color:var(--ochre)">${n.capped?'Ceiling reached — XP alone will not move this.':'Ceiling at level '+n.cap+'.'}</b> ${n.capNote}</p>`:''}
    <section><h3>How to unlock the next level</h3>
      <p>${n.req||'No requirement recorded.'}</p></section>
    <section><h3>Requires</h3>
      ${n.prereq.length?n.prereq.map(p=>reqRow(p[0],p[1])).join(''):'<span class="none">Nothing — this is a root node.</span>'}</section>
    <section><h3>Leads to</h3>
      ${n.unlocks.length?n.unlocks.map(u=>reqRow(u,1)).join(''):'<span class="none">Nothing further yet.</span>'}</section>
    <section><h3>Evidence${n.ev.length?` · ${n.ev.length}`:''}</h3>
      ${n.ev.length?n.ev.map(e=>`<div class="ev"><div class="top mono"><span>${e.d}</span><b>${e.k}</b><span>+${e.x} XP</span></div><p>${e.r}</p></div>`).join(''):'<span class="none">No evidence recorded. Nothing here has been earned yet.</span>'}</section>`;
  P.classList.add('open');
  P.querySelector('#close').onclick=deselect;
  P.querySelectorAll('[data-go]').forEach(b=>b.onclick=()=>{show(b.dataset.go);centre(b.dataset.go)});
  P.scrollTop=0;
}
function centre(id){const p=POS[id];if(!p)return;
  vb.x=p[0]-vb.w/2; vb.y=p[1]-vb.h/2; apply()}
Object.values(els).forEach(n=>{
  n.addEventListener('click',e=>{e.stopPropagation();if(moved>6)return;show(n.dataset.id)});
  n.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();show(n.dataset.id)}});
});
S.addEventListener('click',()=>{if(moved<=6)deselect()});
addEventListener('keydown',e=>{if(e.key==='Escape')deselect()});
"""


def _layout(tree: dict[str, Any]) -> tuple[dict[str, tuple[float, float]], dict[str, int]]:
    """Radial wedge layout: one wedge per tree, tier drives distance from centre.

    Computed here rather than in the browser so positions are identical every
    time the file is regenerated — a tree that rearranged itself daily would be
    unreadable.
    """
    branches = tree["trees"]
    grouped: dict[str, list[dict[str, Any]]] = {b["id"]: [] for b in branches}
    for node in tree["nodes"]:
        grouped.setdefault(node.get("tree", "misc"), []).append(node)

    pos: dict[str, tuple[float, float]] = {}
    side: dict[str, int] = {}
    count = len(branches)
    for bi, branch in enumerate(branches):
        centre = 2 * math.pi * bi / count - math.pi / 2
        wedge = 2 * math.pi / count
        tiers: dict[int, list[dict[str, Any]]] = {}
        for node in grouped.get(branch["id"], []):
            tiers.setdefault(node.get("tier", 1), []).append(node)
        for tier, members in sorted(tiers.items()):
            members.sort(key=lambda n: n["name"])
            # Compressed, not linear: most trees stop around tier 5, so linear
            # growth would strand the few tier-9 nodes far outside everything.
            radius = 300 + (tier ** 0.82) * 165
            span = wedge * 0.74
            k = len(members)
            for i, node in enumerate(members):
                angle = centre if k == 1 else centre - span / 2 + span * i / (k - 1)
                # Three-phase radial stagger: neighbours in a crowded tier sit on
                # different rings, so angular spacing alone never has to clear a
                # full node diameter.
                phase = (i % 3) - 1
                r = radius + phase * 58
                pos[node["id"]] = (r * math.cos(angle), r * math.sin(angle))
                # Neighbours in a crowded tier alternate their label above and
                # below the disc, so adjacent names cannot land on each other.
                side[node["id"]] = -1 if phase == 0 else 1
    return pos, side


# What it takes to lift each ceiling. The tree is only useful if it names the
# next kind of evidence, not just the number it is stuck on.
CAP_NOTE = {
    1: "Only questions are recorded here. Studying it properly lifts this to 2; "
       "practising it lifts it to 4.",
    2: "Reading and study top out at level 2. Practising this — actually doing it, "
       "however badly — lifts the ceiling to 4.",
    4: "Practice tops out at level 4. Building or shipping something with it lifts "
       "the ceiling to 6.",
    6: "Shipped work tops out at level 6. Using it for real — paid, delivered, or "
       "relied on by someone else — lifts the ceiling to 8.",
    8: "Real-world use tops out at level 8. Levels 9 and 10 need repeated success: "
       "three or more real results spanning at least six months.",
}


def cmd_dashboard(args: argparse.Namespace) -> int:
    tree = load_tree(args.tree)
    recompute_all(tree)
    idx = node_index(tree)
    pos, side = _layout(tree)
    e = html.escape
    branches = {b["id"]: b for b in tree["trees"]}

    # Frame the dense core rather than the handful of tier-9 outliers: fitting
    # the absolute extent would shrink the readable body of the tree to nothing.
    radii = sorted(math.hypot(x, y) for x, y in pos.values())
    core = radii[int(len(radii) * 0.93)] if radii else 800
    extent = core + 210

    p: list[str] = []
    w = p.append
    w(f"<title>{e(tree['player']['name'])} — Skill Tree</title>")
    w(f"<style>{TREE_CSS}</style>")
    w('<div id="stage"><svg id="svg" preserveAspectRatio="xMidYMid meet" '
      'role="application" aria-label="Personal skill tree"><g id="cam">')

    # ---- edges, drawn first so nodes sit on top ----
    for node in tree["nodes"]:
        if node["id"] not in pos:
            continue
        x2, y2 = pos[node["id"]]
        for req in node.get("prerequisites", []):
            target, need = (req.get("node"), req.get("level", 1)) if isinstance(req, dict) \
                else (req, 1)
            if target not in pos:
                continue
            x1, y1 = pos[target]
            parent = idx[target]
            cls = "edge"
            if parent.get("tree") != node.get("tree"):
                cls += " cross"
            if parent.get("level", 0) >= need:
                cls += " done"
            # Curve toward the centre so long cross-tree links stay legible.
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            w(f'<path class="{cls}" data-a="{e(target)}" data-b="{e(node["id"])}" '
              f'd="M{x1:.0f} {y1:.0f} Q{mx * 0.82:.0f} {my * 0.82:.0f} {x2:.0f} {y2:.0f}"/>')

    # Thirteen full branch names will not fit around the rim at a readable
    # size, so the rim carries short forms; the full name is in the panel.
    SHORT = {
        "entrepreneurship": "Entrepreneurship", "growth_ops": "Growth Ops",
        "ai_automation": "AI & Automation", "content_youtube": "YouTube",
        "filmmaking": "Filmmaking", "art": "Art", "fitness": "Fitness",
        "money": "Money", "technology": "Technology", "learning": "Learning",
        "personal_development": "Personal Dev", "life_independence": "Independence",
        "cross": "Cross-Tree",
    }

    # ---- branch labels at the outer edge of each wedge ----
    count = len(tree["trees"])
    for bi, branch in enumerate(tree["trees"]):
        members = [n for n in tree["nodes"] if n.get("tree") == branch["id"] and n["id"] in pos]
        if not members:
            continue
        top = max(n.get("tier", 1) for n in members)
        angle = 2 * math.pi * bi / count - math.pi / 2
        # Sit at the rim of the framed area, but never beyond it, so no branch
        # name is cropped by the initial fit.
        r = min(300 + (top ** 0.82) * 165 + 175, extent - 95)
        w(f'<text class="branch-label" x="{r * math.cos(angle):.0f}" '
          f'y="{r * math.sin(angle):.0f}">'
          f'{e(SHORT.get(branch["id"], branch["name"]))}</text>')

    # ---- nodes ----
    R = 27
    circ = 2 * math.pi * (R + 7)
    for node in tree["nodes"]:
        if node["id"] not in pos:
            continue
        x, y = pos[node["id"]]
        has = node.get("xp", 0) > 0
        cls = "node"
        cls += " has" if has else (" avail" if node.get("status") != "Locked" else " idle")
        if not has:
            cls += " idle"
        if node.get("hidden"):
            cls += " hidden"
        label = "???" if node.get("hidden") and not has else node["name"]
        w(f'<g class="{cls}" data-id="{e(node["id"])}" tabindex="0" role="button" '
          f'transform="translate({x:.0f},{y:.0f})">')
        w(f'<title>{e(label)} — level {node["level"]}</title>')
        w(f'<circle class="halo" r="{R + 20}"/>')
        w(f'<circle class="disc" r="{R}"/>')
        if node.get("level", 0) > 0:
            on = circ * node["level"] / 10
            w(f'<circle class="ring" r="{R + 7}" stroke-dasharray="{on:.1f} {circ - on:.1f}"/>')
        if node.get("level_cap", 10) < 10 and node.get("xp", 0) > 0:
            blocked = circ * (10 - node["level_cap"]) / 10
            w(f'<circle class="cap" r="{R + 13}" stroke-dasharray="0 {circ - blocked:.1f} '
              f'{blocked:.1f}" stroke-dashoffset="0"/>')
        w(f'<text class="lv mono">{node["level"] if has else "·"}</text>')
        if node.get("sharpness") in ("rusting", "dormant"):
            w(f'<circle class="rust" cx="{R - 4}" cy="{-R + 6}" r="4.5"/>')
        # Two-line label so long names stay inside the node spacing.
        words = label.split()
        line1, line2 = label, ""
        if len(label) > 17 and len(words) > 1:
            half = len(label) / 2
            best, run = 0, 0
            for i, word in enumerate(words[:-1]):
                run += len(word) + 1
                if abs(run - half) < abs(best - half):
                    best, split = run, i + 1
            line1 = " ".join(words[:split])
            line2 = " ".join(words[split:])
        if side.get(node["id"], 1) < 0:
            top_y = -R - 16 - (17 if line2 else 0)
            w(f'<text class="lbl" y="{top_y}">{e(line1)}</text>')
            if line2:
                w(f'<text class="lbl" y="{top_y + 17}">{e(line2)}</text>')
        else:
            w(f'<text class="lbl" y="{R + 21}">{e(line1)}</text>')
            if line2:
                w(f'<text class="lbl" y="{R + 38}">{e(line2)}</text>')
        w("</g>")

    w("</g></svg></div>")

    # ---- detail panel + chrome ----
    w('<aside id="panel" aria-live="polite"></aside>')
    w('<div id="hint" class="mono">Drag to pan · scroll to zoom · click a node</div>')
    w('<div id="zoom"><button id="zin" aria-label="Zoom in">+</button>'
      '<button id="zout" aria-label="Zoom out">−</button>'
      '<button id="zfit" aria-label="Fit tree">⤢</button></div>')
    w('<div id="legend">'
      '<span><i class="has"></i>evidenced</span>'
      '<span><i class="av"></i>available</span>'
      '<span><i></i>locked</span>'
      '<span><i class="cap"></i>ochre arc = evidence ceiling</span>'
      '<span>ring = level</span></div>')

    # ---- data ----
    payload = {}
    for node in tree["nodes"]:
        if node["id"] not in pos:
            continue
        lo, hi = xp_span_for_level(node["level"])
        payload[node["id"]] = {
            "name": "???" if node.get("hidden") and node.get("xp", 0) <= 0 else node["name"],
            "treeName": branches.get(node.get("tree"), {}).get("name", ""),
            "level": node["level"],
            "levelName": LEVEL_NAMES[node["level"]],
            "status": node.get("status", ""),
            "xp": round(node.get("xp", 0)),
            "next": 0 if node["level"] >= 10 else round(hi - node.get("xp", 0)),
            "cap": node.get("level_cap", 10),
            "capped": bool(node.get("capped")),
            "capNote": CAP_NOTE.get(node.get("level_cap", 10), ""),
            "conf": node.get("confidence", "none"),
            "rust": node["sharpness"] if node.get("sharpness") in ("rusting", "dormant") else "",
            "req": node.get("unlock_requirement", ""),
            "prereq": [[r["node"], r.get("level", 1)] if isinstance(r, dict) else [r, 1]
                       for r in node.get("prerequisites", [])],
            "unlocks": node.get("next_unlock", []),
            "ev": [{"d": ev.get("date", ""), "k": ev.get("kind", ""),
                    "x": round(ev.get("xp", 0)), "r": ev.get("reason", "")}
                   for ev in node.get("evidence", [])],
        }
    w("<script>")
    w("const DATA=" + json.dumps(payload, ensure_ascii=False) + ";")
    w("const POS=" + json.dumps({k: [round(v[0]), round(v[1])] for k, v in pos.items()}) + ";")
    w(f"const VB0={{x:{-extent},y:{-extent},w:{2 * extent},h:{2 * extent},cx:0,cy:0}};")
    w(TREE_JS)
    w("</script>")

    path = args.out or DASH_PATH
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(p))
    print(f"Wrote {path} — {len(payload)} nodes")
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
