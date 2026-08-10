---
description: Run a Personal Skill Tree update, calibration, or status view
argument-hint: "[update | calibrate | show | quests | status]"
---

Use the `personal-skill-tree` skill. Argument: `$ARGUMENTS` (default: `update`).

- **update** — review activity since `player.last_update`, extract evidence,
  apply it through the engine, regenerate the markdown and dashboard, and give
  the daily report. If nothing meaningful happened, say so and apply nothing.
- **calibrate** — run the first-run intake tree by tree, then encode the
  answers as dated retrospective events.
- **show** — read the tree and present the current state. Do not award XP.
- **quests** — regenerate 3–5 quests, each requiring a real-world artefact.
- **status** — run `scripts/skilltree.py status` and summarise.

Read the JSON before saying anything about levels. Never hand-edit it.
