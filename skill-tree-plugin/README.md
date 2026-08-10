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
scripts/seed.py                       one-time bootstrap (destroys history if re-run)
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

155 nodes across 13 trees. Calibrated 2026-08-10 from an exported Claude memory
file: 48 nodes carry evidence, 107 do not. Player level 4, 5,290 XP.

The seed itself ships at all zeros — structure, no claims. Every level in the
file was produced by `apply`, from an auditable event with a stated reason. The
calibration input is kept at `data/updates/2026-08-10-calibration.json` so any
level can be traced back to the specific thing that earned it.

What the calibration found, without being told to look for it:

- **Entrepreneurship is populated up to level 3 and Sales is at zero.** Offer
  Creation 3, Copywriting 3, Client Acquisition 2, Positioning 2 — and no
  evidence of a close, because there are no paying clients yet. The tree cannot
  round that up, so it doesn't.
- **The evidenced build and the declared direction disagree.** The evidence
  supports Builder (Technical Generalist); the stated direction is AI Growth
  Operator. Both are recorded, and the gap between them is the point.
- **Execution scores 4.0/10 on 5,290 XP** of almost entirely action-class
  evidence, because the consistency and operations nodes are empty. Starting is
  not finishing, and the attribute is built to say so.
- **Zapier is a listed primary tool sitting at 15 XP of exploration**, capped at
  level 2 until something ships.

`build` is set at medium confidence with the mismatch recorded in a note. That
field is meant to be set rarely and deliberately, not refreshed after a good week.

## Dashboard

`dashboard/index.html` is self-contained, theme-aware, and regenerated from the
JSON — XP bars, locked nodes greyed, `???` for hidden branches, milestone and
quest panels. Regenerate it after every update so it never disagrees with the
data.
