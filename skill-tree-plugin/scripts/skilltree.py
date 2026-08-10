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
DASH_CSS = """
/* Palette from Brajan's own AIGO brand guide: cream, near-black, signal red.
   Neutrals are warm — biased toward the accent — rather than pure grey.
   Signal red is the accent and is spent only on progress. Rust and cap
   warnings use ochre so semantic state never collides with the accent. */
:root{
  --ground:#F7F6F2; --panel:#FFFFFF; --sunken:#EFEDE6;
  --ink:#131311; --ink-2:#5A5751; --ink-3:#8B877E;
  --line:#E2DFD5; --line-2:#D3CFC2;
  --accent:#FF4D3D; --accent-soft:#FFE3DF;
  --warn:#B8792B; --warn-soft:#F6E8D2;
  --blocked:#CFCABB;
  --seg-empty:#E4E1D7;
}
@media (prefers-color-scheme:dark){
  :root:not([data-theme="light"]){
    --ground:#131311; --panel:#1B1A17; --sunken:#100F0E;
    --ink:#F7F6F2; --ink-2:#A8A399; --ink-3:#736F66;
    --line:#2B2924; --line-2:#3A372F;
    --accent:#FF5C4C; --accent-soft:#3A211C;
    --warn:#D9A05B; --warn-soft:#33260F;
    --blocked:#3D3A32;
    --seg-empty:#26241F;
  }
}
:root[data-theme="dark"]{
  --ground:#131311; --panel:#1B1A17; --sunken:#100F0E;
  --ink:#F7F6F2; --ink-2:#A8A399; --ink-3:#736F66;
  --line:#2B2924; --line-2:#3A372F;
  --accent:#FF5C4C; --accent-soft:#3A211C;
  --warn:#D9A05B; --warn-soft:#33260F;
  --blocked:#3D3A32;
  --seg-empty:#26241F;
}

*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
  padding:34px 20px 90px;
}
.wrap{max-width:1180px;margin:0 auto;display:flex;flex-direction:column;gap:22px}

.mono{font-family:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace}
.num{font-variant-numeric:tabular-nums}

/* ---- masthead ---- */
.mast{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:14px;
  padding-bottom:18px;border-bottom:2px solid var(--ink)}
.mast h1{margin:0;font-size:clamp(22px,3.4vw,32px);font-weight:800;letter-spacing:-.02em;
  text-wrap:balance;line-height:1.05}
.mast h1 .dot{color:var(--accent)}
.mast .stamp{font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3)}

/* ---- readout strip ---- */
.readout{display:grid;gap:1px;background:var(--line);border:1px solid var(--line);
  grid-template-columns:repeat(auto-fit,minmax(150px,1fr))}
.cell{background:var(--panel);padding:14px 16px;display:flex;flex-direction:column;gap:5px}
.cell .k{font-size:10px;letter-spacing:.15em;text-transform:uppercase;color:var(--ink-3)}
.cell .v{font-size:27px;font-weight:750;line-height:1;letter-spacing:-.02em}
.cell .v small{font-size:14px;font-weight:500;color:var(--ink-3)}
.cell .v.txt{font-size:16px;font-weight:650;line-height:1.25;letter-spacing:0}

/* ---- the finding ---- */
.finding{border:1px solid var(--line-2);border-left:3px solid var(--accent);
  background:var(--panel);padding:18px 20px;display:flex;flex-direction:column;gap:10px}
.finding .eyebrow{font-size:10px;letter-spacing:.16em;text-transform:uppercase;color:var(--accent)}
.finding .pair{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:15px}
.finding .pair b{font-weight:700}
.finding .vs{font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--ink-3)}
.finding p{margin:0;color:var(--ink-2);font-size:14px;max-width:74ch}

/* ---- section ---- */
.sec{display:flex;flex-direction:column;gap:12px}
.sec>h2{margin:0;font-size:11px;letter-spacing:.16em;text-transform:uppercase;color:var(--ink-3);
  padding-bottom:7px;border-bottom:1px solid var(--line)}

/* ---- attributes ---- */
.attrs{display:grid;gap:10px 26px;grid-template-columns:repeat(auto-fit,minmax(270px,1fr))}
.attr{display:grid;grid-template-columns:1fr 96px 30px;gap:11px;align-items:center;font-size:13.5px}
.meter{height:6px;background:var(--seg-empty);position:relative;overflow:hidden}
.meter i{position:absolute;inset:0 auto 0 0;background:var(--accent);display:block}
.attr .n{text-align:right;color:var(--ink-2);font-size:12px}

/* ---- trees ---- */
.trees{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(340px,1fr))}
.branch{background:var(--panel);border:1px solid var(--line);display:flex;flex-direction:column}
.branch>header{padding:13px 16px;border-bottom:1px solid var(--line);
  display:flex;justify-content:space-between;align-items:baseline;gap:10px}
.branch h3{margin:0;font-size:14.5px;font-weight:700;letter-spacing:-.01em}
.branch .count{font-size:11px;color:var(--ink-3);white-space:nowrap}
.branch .desc{padding:10px 16px 0;margin:0;font-size:12.5px;color:var(--ink-3);max-width:60ch}
.rows{display:flex;flex-direction:column;padding:6px 0 4px}
.row{display:grid;grid-template-columns:1fr auto;gap:3px 12px;padding:8px 16px;align-items:center}
.row .nm{font-size:13.5px;font-weight:550;display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.row .lv{font-size:11px;color:var(--ink-3);white-space:nowrap;letter-spacing:.04em}
.row .segs{grid-column:1/-1}
.row.idle .nm{color:var(--ink-3);font-weight:500}

/* Level as 10 segments. Everything above the evidence cap is drawn blocked —
   the ceiling is the point of the system, so it is shown, not annotated. */
.segs{display:flex;gap:2px;height:9px;margin-top:2px}
.segs span{flex:1;background:var(--seg-empty)}
.segs span.on{background:var(--accent)}
.segs span.cap{background:repeating-linear-gradient(135deg,var(--blocked) 0 2px,transparent 2px 4px)}
.segs span.tip{position:relative;overflow:hidden}
.segs span.tip::after{content:"";position:absolute;inset:0 auto 0 0;background:var(--accent);width:var(--p,0%)}

.chip{font-size:9.5px;letter-spacing:.09em;text-transform:uppercase;padding:2px 6px;
  border:1px solid currentColor;color:var(--ink-3);white-space:nowrap;line-height:1.4}
.chip.warn{color:var(--warn);background:var(--warn-soft)}
.chip.cap{color:var(--warn)}
.chip.ready{color:var(--accent);background:var(--accent-soft)}
.hidden-row{padding:9px 16px;border-top:1px dashed var(--line);
  font-size:12px;color:var(--ink-3);display:flex;justify-content:space-between;gap:10px}
.locked-row{padding:9px 16px;font-size:12px;color:var(--ink-3);border-top:1px solid var(--line)}

/* ---- quests ---- */
.quests{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(300px,1fr))}
.quest{background:var(--panel);border:1px solid var(--line);padding:15px 17px;
  display:flex;flex-direction:column;gap:8px}
.quest.main{border-color:var(--accent);border-top:3px solid var(--accent)}
.quest h4{margin:0;font-size:14.5px;font-weight:700;letter-spacing:-.01em;text-wrap:balance}
.quest p{margin:0;font-size:13px;color:var(--ink-2);max-width:62ch}
.quest dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:3px 10px;font-size:12px}
.quest dt{color:var(--ink-3);letter-spacing:.09em;text-transform:uppercase;font-size:9.5px;padding-top:2px}
.quest dd{margin:0;color:var(--ink-2)}
.diff{color:var(--accent);letter-spacing:3px;font-size:11px}

/* ---- lists ---- */
.two{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(320px,1fr))}
.panel{background:var(--panel);border:1px solid var(--line);padding:6px 0}
.li{display:flex;justify-content:space-between;gap:12px;padding:9px 16px;font-size:13.5px;
  border-top:1px solid var(--line);align-items:baseline}
.li:first-child{border-top:0}
.li .r{font-size:11px;color:var(--ink-3);white-space:nowrap}
.li.off{color:var(--ink-3)}
.li .sub{display:block;font-size:11.5px;color:var(--ink-3);margin-top:3px}

.foot{font-size:11px;color:var(--ink-3);border-top:1px solid var(--line);padding-top:14px;
  max-width:74ch}
@media (max-width:560px){
  body{padding:24px 14px 70px}
  .attr{grid-template-columns:1fr 70px 28px}
}
"""


def _segments(node: dict[str, Any]) -> str:
    """Ten level segments, with the evidence ceiling drawn as blocked-out."""
    level = node.get("level", 0)
    cap = node.get("level_cap", 10)
    lo, hi = xp_span_for_level(level)
    pct = 0 if hi <= lo else max(0, min(100, 100 * (node.get("xp", 0) - lo) / (hi - lo)))
    out = []
    for i in range(1, 11):
        if i <= level:
            out.append('<span class="on"></span>')
        elif i > cap:
            out.append('<span class="cap"></span>')
        elif i == level + 1:
            out.append(f'<span class="tip" style="--p:{pct:.0f}%"></span>')
        else:
            out.append("<span></span>")
    return '<div class="segs" aria-hidden="true">' + "".join(out) + "</div>"


def cmd_dashboard(args: argparse.Namespace) -> int:
    tree = load_tree(args.tree)
    recompute_all(tree)
    player = tree["player"]
    idx = node_index(tree)
    e = html.escape
    p: list[str] = []
    w = p.append

    evidenced = [n for n in tree["nodes"] if n.get("xp", 0) > 0]

    w(f"<title>{e(player['name'])} — Personal Skill Tree</title>")
    w(f"<style>{DASH_CSS}</style>")
    w('<div class="wrap">')

    # ---- masthead ----
    w('<header class="mast">')
    w(f'<h1>{e(player["name"].upper())} — PERSONAL SKILL TREE<span class="dot">.</span></h1>')
    w(f'<div class="stamp mono">Calibrated {e(player.get("last_update") or "never")} · '
      f'{len(evidenced)}/{len(tree["nodes"])} nodes evidenced</div>')
    w("</header>")

    # ---- readout ----
    unlocked = sum(1 for m in tree.get("milestones", []) if m.get("unlocked"))
    build = tree.get("build", {})
    w('<div class="readout">')
    w(f'<div class="cell"><span class="k mono">Player level</span>'
      f'<span class="v num mono">{player["player_level"]}</span></div>')
    w(f'<div class="cell"><span class="k mono">Total XP</span>'
      f'<span class="v num mono">{player["total_xp"]:,.0f}</span></div>')
    w(f'<div class="cell"><span class="k mono">Milestones</span>'
      f'<span class="v num mono">{unlocked}<small>/{len(tree.get("milestones", []))}</small></span></div>')
    w(f'<div class="cell"><span class="k mono">Evidenced build</span>'
      f'<span class="v txt">{e(build.get("primary_class") or "Undetermined")}</span></div>')
    w("</div>")

    # ---- the finding: evidenced build vs declared direction ----
    declared = build.get("declared_direction")
    if declared and build.get("primary_class") and declared != build["primary_class"]:
        w('<section class="finding">')
        w('<span class="eyebrow mono">What the evidence says</span>')
        w('<div class="pair"><b>' + e(build["primary_class"]) + '</b>'
          '<span class="vs mono">evidenced &nbsp;/&nbsp; declared</span>'
          '<b>' + e(declared) + "</b></div>")
        if build.get("note"):
            w(f"<p>{e(build['note'])}</p>")
        w("</section>")

    # ---- attributes ----
    w('<section class="sec"><h2>Core attributes</h2><div class="attrs">')
    for name, data in tree.get("attributes", {}).items():
        w(f'<div class="attr"><span>{e(name.replace("_", " ").title())}</span>'
          f'<span class="meter"><i style="width:{10 * data["value"]:.0f}%"></i></span>'
          f'<span class="n num mono">{data["value"]}</span></div>')
    w("</div></section>")

    # ---- trees ----
    w('<section class="sec"><h2>Skill trees</h2><div class="trees">')
    for branch in tree["trees"]:
        nodes = [n for n in tree["nodes"] if n.get("tree") == branch["id"]]
        visible = [n for n in nodes if not n.get("hidden")]
        hidden = [n for n in nodes if n.get("hidden")]
        active = sorted([n for n in visible if n.get("xp", 0) > 0],
                        key=lambda n: (-n.get("level", 0), -n.get("xp", 0)))
        ready = [n for n in visible if n.get("xp", 0) == 0 and n.get("status") != "Locked"]
        locked = [n for n in visible if n.get("xp", 0) == 0 and n.get("status") == "Locked"]

        w('<article class="branch">')
        w(f'<header><h3>{e(branch["name"])}</h3>'
          f'<span class="count mono num">{len(active)}/{len(visible)}</span></header>')
        if branch.get("description"):
            w(f'<p class="desc">{e(branch["description"])}</p>')
        w('<div class="rows">')
        for node in active:
            chips = ""
            if node.get("capped"):
                chips += f'<span class="chip cap mono">cap {node["level_cap"]}</span>'
            if node.get("sharpness") in ("rusting", "dormant"):
                days = node.get("days_since_progress")
                label = f'{node["sharpness"]} {days}d' if days is not None else node["sharpness"]
                chips += f'<span class="chip warn mono">{e(label)}</span>'
            w('<div class="row">')
            w(f'<span class="nm">{e(node["name"])}{chips}</span>')
            w(f'<span class="lv mono num">Lv {node["level"]} · {e(LEVEL_NAMES[node["level"]])}</span>')
            w(_segments(node))
            w("</div>")
        for node in ready[:4]:
            w('<div class="row idle">')
            w(f'<span class="nm">{e(node["name"])}'
              f'<span class="chip ready mono">ready</span></span>')
            w('<span class="lv mono">no evidence</span>')
            w("</div>")
        if len(ready) > 4:
            w(f'<div class="locked-row mono">+{len(ready) - 4} more available, no evidence yet</div>')
        w("</div>")
        if locked:
            w(f'<div class="locked-row mono">{len(locked)} locked behind prerequisites</div>')
        if hidden:
            w(f'<div class="hidden-row mono"><span>???</span>'
              f'<span>{len(hidden)} hidden</span></div>')
        w("</article>")
    w("</div></section>")

    # ---- quests ----
    quests = tree.get("quests", []) or []
    if quests:
        w('<section class="sec"><h2>Current quests</h2><div class="quests">')
        for i, quest in enumerate(quests):
            cls = "quest main" if i == 0 else "quest"
            stars = "★" * quest.get("difficulty", 3) + "☆" * (5 - quest.get("difficulty", 3))
            w(f'<article class="{cls}">')
            w(f'<h4>{e(quest["name"])}</h4>')
            w(f'<p>{e(quest.get("description", ""))}</p>')
            w("<dl>")
            w(f'<dt class="mono">Reward</dt><dd>{e(quest.get("reward", "—"))}</dd>')
            w(f'<dt class="mono">Proof</dt><dd>{e(quest.get("proof", "—"))}</dd>')
            w("</dl>")
            w(f'<span class="diff" title="Difficulty">{stars}</span>')
            w("</article>")
        w("</div></section>")

    # ---- nearest unlocks + milestones ----
    w('<div class="two">')
    near = nearest_unlocks(tree, idx)
    w('<section class="sec"><h2>Nearest unlocks</h2><div class="panel">')
    if near:
        for item in near:
            right = "ready" if item["ready"] else f'{item["pct"]}%'
            sub = "" if not item["missing"] else \
                f'<span class="sub">Missing: {e("; ".join(item["missing"]))}</span>'
            w(f'<div class="li"><span>{e(item["name"])}{sub}</span>'
              f'<span class="r mono">{right}</span></div>')
    else:
        w('<div class="li off">Nothing close yet.</div>')
    w("</div></section>")

    w('<section class="sec"><h2>Milestones</h2><div class="panel">')
    for milestone in tree.get("milestones", []):
        got = milestone.get("unlocked")
        right = e(milestone.get("date") or "") if got else "locked"
        w(f'<div class="li{"" if got else " off"}"><span>{"✓ " if got else ""}'
          f'{e(milestone["name"])}</span><span class="r mono">{right}</span></div>')
    w("</div></section>")
    w("</div>")

    w('<footer class="foot">Generated from PERSONAL_SKILL_TREE.json by '
      'scripts/skilltree.py. Levels are capped by the class of evidence behind them — '
      'hatched segments mark a ceiling that reading cannot lift, only doing.</footer>')
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
