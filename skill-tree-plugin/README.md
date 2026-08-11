# Personal Skill Tree

An RPG progression system for real skills, built so that it cannot be gamed by
talking to it.

The design problem with "Claude, track my progress" is that the thing doing the
tracking is the same thing being persuaded. Ask an agent every day whether you
improved and it will find a way to say yes. So scoring does not live in the
prompt here — it lives in `scripts/skilltree.py`, which has no opinion about
whether you feel productive.

**Claude classifies evidence. The engine prices it.**

## Layout

```
skills/personal-skill-tree/SKILL.md   how Claude runs an update
commands/skill-tree.md                /skill-tree slash command
scripts/skilltree.py                  the engine — all scoring lives here
scripts/structure.py                  the shape: trees, nodes, prerequisites
scripts/seed.py                       one-time bootstrap (destroys history if re-run)
scripts/generalise.py                 the 155 -> 70 node migration, kept as a record
data/PERSONAL_SKILL_TREE.json         source of truth
data/PERSONAL_SKILL_TREE.md           generated, human-readable
dashboard/index.html                  generated, self-contained
```

## Usage

```bash
python3 scripts/skilltree.py status
python3 scripts/skilltree.py apply update.json --dry-run
python3 scripts/skilltree.py apply update.json
python3 scripts/skilltree.py render
python3 scripts/skilltree.py dashboard
```

Or in Claude Code: `/skill-tree update`, `/skill-tree calibrate`, `/skill-tree show`.

## How levels are earned

XP accumulates and drives the level curve. But XP alone cannot raise a level
past the ceiling set by the **class of evidence** on that node:

| Best evidence | Ceiling |
|---|---|
| questions only | 1 |
| knowledge, study | 2 |
| practice | 4 |
| built or shipped | 6 |
| used successfully in the real world | 8 |
| repeated real-world success (≥3 events over ≥180 days) | 10 |

This is the whole idea. A node can hold 5,000 XP of diligent reading and sit at
level 2, flagged `capped`, until something gets built. Verified:

```
After 60 days of pure study: 900 XP, level 2, cap 2, capped=True
```

900 XP is level 6 on the raw curve. It stays at 2. One `project` event on the
same node then moved it to 5 — the reading was real and it counted, it just
could not be cashed until there was something to cash it against.

Alongside that:

- **A 60 XP-per-update budget shared by all discussion-class evidence**, across
  the entire tree. Eight talk events in one update yielded 60 XP total and three
  rejections. You cannot grind levels in a chat window.
- **150 XP per node per update** for ordinary evidence.
- **Levels 8–10 additionally require a track record over time**, not one good result.
- **Milestones** need `occurred: true` and a reason naming the event.
- **Rust**: 45 days without practice flags `rusting`, 120 flags `dormant`.
  Levels never fall — retained knowledge and current sharpness are different
  things and are tracked separately.
- **Execution** is computed as the ratio of doing-XP to total XP, so a tree
  full of reading scores low on it no matter how much XP it holds.

Every event is stored with its date, kind, XP and reason. A level is always
traceable to the specific things that produced it.

## Current state

70 nodes across 10 trees. Calibrated 2026-08-10 from an exported Claude memory
file: 31 nodes carry evidence, 39 do not. Player level 4, 5,290 XP.

The tree originally had 155 nodes, which was too fine-grained to assess honestly
— "Stippling" and "Recovery & Sleep" were separate skills. It was folded down to
70 broader ones by `scripts/generalise.py`, which carried all 106 evidence
events across with their dates and reasons intact and preserved the XP total
exactly. Levels moved only where several narrow nodes genuinely merged; nothing
that mapped one-to-one changed.

The seed itself ships at all zeros — structure, no claims. Every level in the
file was produced by `apply`, from an auditable event with a stated reason. The
calibration input is kept at `data/updates/2026-08-10-calibration.json` so any
level can be traced back to the specific thing that earned it.

What the calibration found, without being told to look for it:

- **The Business tree is populated and Sales is at zero.** Growth Diagnosis &
  Strategy 4, Offer/Pricing/Positioning 3, Copywriting 3, Outreach 2 — and no
  evidence of a close, because there are no paying clients yet. The tree cannot
  round that up, so it doesn't.
- **The evidenced build and the declared direction disagree.** The evidence
  supports Builder (Technical Generalist); the stated direction is AI Growth
  Operator. Both are recorded, and the gap between them is the point.
- **Execution scores 4.5/10 on 5,290 XP** of almost entirely action-class
  evidence, because the consistency and delivery nodes are empty. Starting is
  not finishing, and the attribute is built to say so.
- **Automation Tools sits at 15 XP of pure exploration**, ceiling 2, despite
  Zapier being one of your listed primary tools.

`build` is set at medium confidence with the mismatch recorded in a note. That
field is meant to be set rarely and deliberately, not refreshed after a good week.

## Updating the tree

There is no scheduled job. Updates happen when you ask for one — `/skill-tree
update` in Claude Code, or `python3 scripts/skilltree.py apply <file>` directly.

A daily Routine used to run this at 19:00 UTC. It was removed on 2026-08-11.
Worth recording why, in case it looks like an omission later: a scheduled cloud
session gets the repo and nothing else — no chat history, no memory, no activity
feed. It could not see what you had done, so it could only ever prompt you and
wait. The evidence has to come from you either way, which makes the schedule the
least useful part of the loop.

Decay is the one thing that genuinely changed on its own, and it is recomputed
on every `render` and `dashboard` run, so nothing is lost by running those when
you actually have something to record.

## Dashboard

Live at **https://claude.ai/code/artifact/e5f9054b-fa47-4787-acaf-a31c8a355d77**
(private to your account). The daily Routine republishes to that same URL, so
the link stays stable — bookmark it.

It is the tree and nothing else: ten branch cards, each stacking its skills from
foundations at the top down to specialisations at the bottom. Drag to pan,
scroll or pinch to zoom, click any node.

An earlier version fanned all the nodes out radially. It photographed well and
read badly — sectors at different angles put multi-word labels on collision
courses, and three rounds of tuning did not fix it. Cards give every node a
fixed slot, so a label can never land on its neighbour, and depth is just
"further down the card". Card headers carry the branch name and how many of its
skills carry evidence, so the shape of what you have and have not done is
readable before you click anything.

Selecting a node dims the rest of the board, lights its chain, and opens a panel
with its level and XP, what it would take to reach the next level, what it
requires, what it leads to, and every dated piece of evidence behind it with the
reason recorded. Prerequisites and unlocks in the panel are clickable, so you
can walk a chain node by node.

Reading the marks:

- **Disc size** is depth: foundations are the big dots, specialisations taper.
- **Ring** around a disc is level, out of ten.
- **Ochre arc** is the evidence ceiling — the part of the ring that current
  evidence cannot reach. It is drawn *before* you hit it, and the panel names
  the class of evidence that would lift it ("practising this lifts the ceiling
  to 4"). This is the whole system in one graphic.
- **Filled red discs** carry evidence; hollow ones are available; dim ones are
  locked; `???` are hidden until their prerequisites are met.
- **Ochre dot** on a disc means rusting.
- **Dashed links** arc between cards — those are the cross-tree specialisations,
  kept quiet until you select one.

Layout is computed in Python at generation time, not in the browser, so node
positions are identical on every regeneration. The card packing picks whichever
row count lands the board closest to a screen's proportions.

The page commits to a single dark treatment rather than shipping a light
variant, and paints every colour explicitly so it holds on any host background.

Regenerate with `python3 scripts/skilltree.py dashboard` after every update, and
republish with the URL above so it never mints a second page.
