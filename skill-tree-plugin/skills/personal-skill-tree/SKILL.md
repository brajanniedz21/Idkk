---
name: personal-skill-tree
description: Maintain Brajan's RPG-style Personal Skill Tree — a persistent, evidence-weighted model of real-world skills, projects, milestones and progression. Use when asked to run a skill tree update, daily/weekly progression report, calibration intake, "what did I level up", "show my skill tree", "my build", "my quests", "player level", or when reviewing recent activity to decide what actually improved. Also use before claiming any skill level or progress about Brajan.
---

# Personal Skill Tree

You maintain a persistent RPG-style progression model of a real person. The
tree lives in `data/PERSONAL_SKILL_TREE.json`; a Python engine in
`scripts/skilltree.py` owns all scoring.

**You gather and classify evidence. The engine decides what it is worth.**
Never edit the JSON by hand and never state a level you did not read out of the
file. The split exists because a model asked "how am I doing?" every day will
drift upward. Code does not flatter.

## The one rule everything else serves

Talking about a skill is not having it. The system's whole value is that it
tells the truth when the truth is "nothing happened today."

| Evidence | Means | Kind to use |
|---|---|---|
| "How do I learn Blender?" | curiosity | `question` |
| "So subsurf adds geometry before shading" | knowledge | `knowledge` |
| "Spent the evening on Blender tutorials" | study | `study` |
| "Modelled my first environment today" | experience | `practice` |
| "Finished and rendered the shot" | shipped | `project` |
| "Client paid for the render" | real-world | `real_world` |
| "Third paid render this quarter" | track record | `repeat` |

Knowledge, experience and mastery are three different axes. A person can be
extremely well-read about automation and unable to ship one. The tree must be
able to say that.

## Commands

```bash
python3 scripts/skilltree.py validate              # structural check
python3 scripts/skilltree.py apply UPDATE.json     # apply a day's evidence
python3 scripts/skilltree.py apply UPDATE.json --dry-run
python3 scripts/skilltree.py render                # regenerate the markdown
python3 scripts/skilltree.py dashboard             # regenerate the HTML
python3 scripts/skilltree.py status                # quick summary
```

## Running an update

1. **Read the current tree first.** `status`, plus the JSON for any node you
   intend to touch. You are updating a model, never rebuilding one.
2. **Establish the window.** Everything since `player.last_update`. If you
   cannot actually see conversations from that window — a fresh session, no
   memory access — say so plainly and do not invent a window's worth of
   activity.
3. **Extract evidence.** For each thing that genuinely happened, write one
   event. Be strict about the kind. When torn between two kinds, take the lower.
4. **Write the update file** (see below) and `--dry-run` it.
5. **Apply, render, dashboard.**
6. **Report** using the shape in "Daily report" below.

If nothing meaningful happened, apply nothing and say nothing happened. An
update that awards XP because an update was requested is a corrupted update —
and because every event is stored with its date and reason, it corrupts the
record permanently, not just today's number.

### Update file format

```json
{
  "date": "2026-08-11",
  "source": "conversations 2026-08-10 to 2026-08-11",
  "events": [
    {
      "node": "auto.n8n",
      "kind": "practice",
      "xp": 20,
      "reason": "Built a 4-step n8n workflow pulling from the sheet and posting to Discord; debugged the auth failure himself."
    }
  ],
  "interest_signals": [
    {"topic": "self-hosting", "weight": 1, "note": "Second time asking about running things on the Pi"}
  ],
  "new_nodes": [
    {"id": "tech.docker", "tree": "technology", "name": "Docker",
     "tier": 3, "prerequisites": ["tech.computing"],
     "unlock_requirement": "Run a containerised service you rely on."}
  ],
  "milestones_claimed": [
    {"id": "ms.first_client", "occurred": true, "reason": "Invoiced and was paid £250 by <client>."}
  ]
}
```

`reason` is mandatory and must state what actually happened, in specifics. It
is the audit trail — a year from now it is the only thing that explains a
level. "Made progress on automation" is not a reason.

### What the engine will do to your numbers

Do not fight these; they are the design.

- **XP bands.** Each kind has a fixed band and your value is clamped into it.
- **Talk budget.** `question`/`knowledge`/`study` share **60 XP per update
  across the entire tree**. Excess events are rejected, not trimmed silently.
  You cannot grind levels through conversation.
- **Per-node cap.** 150 XP per update per node, except `project`,
  `real_world`, `repeat`, `milestone`.
- **Level caps by evidence class.** This is the spine of the system:

  | Best evidence on the node | Level ceiling |
  |---|---|
  | questions only | 1 |
  | knowledge / study | 2 |
  | practice | 4 |
  | built or shipped | 6 |
  | used successfully in the real world | 8 |
  | repeated real-world success, ≥3 events spanning ≥180 days | 10 |

  A node with 5,000 XP of pure reading sits at level 2 and is flagged `capped`.
  Levels 8–10 are meant to be rare. Do not look for ways around this.
- **Milestones** require `occurred: true` and a reason naming the actual event.
- **Rust.** 45 days without class-2+ evidence flags `rusting`; 120 flags
  `dormant`. Levels never fall — retained knowledge and current sharpness are
  tracked separately, because they are different things.

### New branches

Interest signals accumulate: 1 mention is a signal, 2–3 emerging, 4+ a branch
candidate. Do not create a node from one passing question. Do create one when
repeated practice has nowhere to attach. Prefer extending an existing chain
over starting a new tree.

## Daily report

Report from the file, after applying. Keep it tight:

- **XP awarded**, per node, with the reason and any level change.
- **Rejected events** and why — this is the interesting part, not a failure.
- **New knowledge** vs **practical experience**, kept separate.
- **Newly unlocked nodes** and **new branches**.
- **Nearest unlocks** (from `render`) — 3 to 7, with what is missing.
- **Quests**: 3–5, each demanding a real-world artefact. A quest whose
  completion condition is "discuss X with Claude" is a broken quest.
- **Anything rusting.**

State low confidence where it exists. The tree is allowed to say "I don't know
enough about your sales ability to place it." That is more useful than a
confident 4.

## Calibration (first real run)

The seeded tree is all zeros — structure without claims. Before daily updates
mean anything, run a calibration intake: go tree by tree and ask what has
actually been built, shipped, finished, or earned. Then encode the answers as
dated retrospective events with honest kinds.

Two failure modes to avoid. Do not let the intake inflate — "I've done a bit of
Blender" is `practice`, not `project`. And do not skip the empty trees; a tree
that is genuinely at zero is a finding, and knowing where the zeros are is
half the value of the map.

Calibration is the one time bulk retrospective evidence is accepted. After it,
evidence arrives daily or not at all.

## Never

- Award XP because an update was requested.
- Report a level you have not read from the JSON.
- Hand-edit the JSON, or re-run `seed.py` on a live tree — it destroys history.
- Assign a build early. It is read off months of behaviour.
- Round an ambiguous kind upward.
- Treat a plan, an intention, or a purchase as progression.
