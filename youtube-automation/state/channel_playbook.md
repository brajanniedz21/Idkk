# Make It Manifest Channel Playbook

Last updated: 2026-08-04T11:53:08.680596+00:00
Generated from analytics runs: analytics-2026-08-04-0710 (plus 7 total cycle entries in state/performance_notes.json)

_This file is a distilled operational summary, not the source of truth. `state/performance_notes.json` and `state/video_analytics.json` hold the full history and every underlying evidence entry — nothing here should be trusted over them, and nothing here is ever the only place a finding lives._

## Channel Positioning

Aspirational luxury / manifestation / future-self motivation, cinematic lifestyle imagery. Shorts (fast-cut, upbeat-not-aggressive audio) and long-form ambience/background video (slow, calm, ambient audio) are deliberately different registers — see `config/channel.json.brand_identity` and `short_form_style_guidance`/`long_form_style_guidance` for the current, authoritative statement of this; this section is a pointer, not a duplicate.

## Current Data Limitations

- Analytics scope this generation: `has_analytics_scope=True` (Data API views/likes/comments are always available regardless; retention/watch-time need the Analytics scope and have a processing lag even when granted).
- Retention, CTR, impressions, watch-time, and traffic-source data are not claimed anywhere in this file — CTR/impressions have no API path at all; the others are only ever included when a cycle explicitly pulled them.
- 26 of 50 published videos currently don't join back to their scouted creative attributes (missing `published_video_id` linkage in the queue) — findings below are necessarily blind to those videos' angle/sound/title-pattern.
- No historical per-video snapshots exist yet, so all performance windows are recent-upload cohorts (current cumulative totals for recently-published videos), not true deltas — see `agents/0_orchestrator.md`'s Daily analytics cycle for the exact distinction.
- Sample sizes are still small: 39 Shorts and 11 long-form videos published to date. Most findings below are `observation`/`early_signal`, not `repeated_pattern` or `strong_channel_pattern` — read every confidence label literally.

## Strong Channel Patterns

_None yet._ No finding has persisted across enough batches/dates/controlled variations to earn this tier — see `agents/0_orchestrator.md`'s evidence-level rules. Current same-format baselines, for reference:
- **Shorts** — n=39, median views=256, median age-normalized views/day=56.7, median likes/1000 views=7.02, median comments/1000 views=0.0
- **Long-form** — n=11, median views=5, median age-normalized views/day=2.5, median likes/1000 views=0.0, median comments/1000 views=0.0

## Promising Patterns to Validate

From the most recent narrative analytics finding (`2026-08-01T19:01:43.322871+00:00`, pre-structured-protocol prose, not yet re-derived under the 2026-08-01 evidence-level system — treat as `early_signal` at most):

> Continue weighting toward legacy/sacrifice/earned-over-time narratives with confident-not-aggressive mid-tempo audio (consistent with config/channel.json.brand_identity's luxury/calm/quiet-confidence direction adopted 2026-07-30). No new attributes to deliberately avoid beyond what's already logged 2026-07-29.

## Winning Short-Form Patterns

- "I'm The First. Not The Last." — 1827 views, 38 likes (raw totals from `2026-08-01T19:01:43.322871+00:00`; not yet age-normalized/baselined under the new protocol — treat as `observation`).
- "Nobody Talks About What I Gave Up." — 1736 views, 36 likes (raw totals from `2026-08-01T19:01:43.322871+00:00`; not yet age-normalized/baselined under the new protocol — treat as `observation`).
- "This Took Years. It Looks Like Luck." — 1580 views, 49 likes (raw totals from `2026-08-01T19:01:43.322871+00:00`; not yet age-normalized/baselined under the new protocol — treat as `observation`).

## Winning Long-Form Patterns

Baseline established (n=11) but no specific attribute-level winner has reached `repeated_pattern` confidence yet.

## Underperforming Patterns

- "Nobody Gave Me Permission. I Took It." — 268 views, 1 likes (raw totals from `2026-08-01T19:01:43.322871+00:00`; `observation`-level, upload age not yet controlled for).
- "Everyone's On A Different Clock." — 257 views, 0 likes (raw totals from `2026-08-01T19:01:43.322871+00:00`; `observation`-level, upload age not yet controlled for).

## Audience Fatigue and Cooldowns

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Proven or Promising Title Structures

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Proven or Promising Hook Structures

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Visual Patterns

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Audio Patterns

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Atmosphere and Setting Patterns

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Series Performance

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Upload Cadence Findings

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## CTA Experiments

- `cta-luxury-001` — status: `gathering_data`, hypothesis: One of 3 alternative Shorts CTA phrasings (cta_luxury_future/claim/begin) drives a higher comments-per-1000-views rate than the original control (cta_luxury_control), without hurting views/likes.

## Active Experiments

- `cta-luxury-001` — gathering_data — One of 3 alternative Shorts CTA phrasings (cta_luxury_future/claim/begin) drives a higher comments-per-1000-views rate than the original control (cta_luxury_control), without hurting views/likes.

## Recently Confirmed Experiments

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Inconclusive Experiments

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Rejected Experiments

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Temporarily Retired Ideas

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Exploration Priorities

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Instructions for the Next Scouting Run

- Continue the legacy/sacrifice/earned-over-time angle family for Shorts (repeat bucket) -- this remains the best-supported pattern on a larger sample (n=34).
- No CTA variant preference yet -- keep the balanced rotation; do not promote any variant to control.
- Do not increase Shorts:long-form ratio further based on today's reach-gap finding alone -- the current 5+2 allocation is a direct owner instruction, not an Agent-0-diagnosed change, and is not being revisited on this evidence.

## Contradictions and Uncertainties

_Not yet populated — no analytics cycle has produced structured evidence for this section yet. This is not a gap in the generator; it means the underlying finding doesn't exist as real, traceable data yet. See `state/performance_notes.json` for the full historical record this playbook distills._

## Change Log

- 2026-08-04T11:53:08.680596+00:00: regenerated from 7 cycle entries, 50 joined videos (26 missing attributes), 1 ledger experiments.
- 2026-08-04T07:10:27.563781+00:00: regenerated from 7 cycle entries, 43 joined videos (19 missing attributes), 1 ledger experiments.
- 2026-08-03T07:16:03.402514+00:00: regenerated from 6 cycle entries, 39 joined videos (18 missing attributes), 1 ledger experiments.
- 2026-08-03T00:19:42.699379+00:00: regenerated from 5 cycle entries, 39 joined videos (18 missing attributes), 1 ledger experiments.
- 2026-08-02T07:10:56.680753+00:00: regenerated from 4 cycle entries, 39 joined videos (18 missing attributes), 1 ledger experiments.
- 2026-08-01T19:53:59.473735+00:00: regenerated from 3 cycle entries, 35 joined videos (17 missing attributes), 0 ledger experiments.
- 2026-08-01T19:53:59.428961+00:00: regenerated from 3 cycle entries, 35 joined videos (17 missing attributes), 0 ledger experiments.
- 2026-08-01T19:53:43.260794+00:00: regenerated from 3 cycle entries, 35 joined videos (17 missing attributes), 0 ledger experiments.
