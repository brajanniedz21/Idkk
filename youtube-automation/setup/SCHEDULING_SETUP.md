# Timezone-Aware Scheduling Setup

**Version:** 1.0  
**Status:** P0 production requirement (as of 2026-08-08)  
**Timezone:** Europe/London (configured in `config/channel.json` and `config/runtime.json`)

This document replaces the old fixed-UTC cron approach with timezone-aware scheduling that correctly handles BST/GMT transitions.

## The Problem

The old system used fixed UTC cron expressions (e.g., `0 5 * * *` for 05:00 UTC) to schedule analytics and content jobs. This fails across daylight-saving transitions:

- In spring (GMT → BST), `05:00 UTC` shifts to `06:00 local` (not `05:00 local`)
- In autumn (BST → GMT), `05:00 UTC` shifts to `04:00 local` (not `05:00 local`)

This desync breaks the "analytics before content" ordering and causes the scheduler to publish at unexpected local times.

## The Solution

**Use a timezone-aware scheduler** with `Europe/London` as the source timezone, and convert the desired local times to UTC once per firing, accounting for the current DST offset.

### Desired Job Schedule (Local Time)

From `config/runtime.json.scheduling`:

```
Timezone: Europe/London
Analytics job: 05:00 local
Content job: 06:00 local
```

These times convert to UTC differently depending on whether DST is active:

| Period | Analytics (UTC) | Content (UTC) |
|--------|---|---|
| Winter (GMT, UTC+0) | 05:00 | 06:00 |
| Summer (BST, UTC+1) | 04:00 | 05:00 |

A timezone-aware scheduler converts to this automatically; a fixed UTC cron cannot.

## Implementation: Scheduled Routines

Two Claude Code Remote Routines (scheduled triggers) own the production schedule:

### Routine 1: Analytics Pipeline

```
Name: "YouTube @makeitmanifest daily analytics (Europe/London 05:00)"
Schedule: "0 5 * * *" (interpreted in Europe/London timezone, not UTC)
Prompt (≤150 tokens):

  In the persistent @makeitmanifest workspace, run `python3 scripts/run_analytics.py --date today`.
  Use the configured compliance mode and current repository specs.
  Return only: data freshness, available metrics, findings permitted by policy,
  experiment status, and blockers.

Created: [setup phase]
Enabled: yes
```

### Routine 2: Content Production Pipeline

```
Name: "YouTube @makeitmanifest daily content (Europe/London 06:00)"
Schedule: "0 6 * * *" (interpreted in Europe/London timezone, not UTC)
Prompt (≤150 tokens):

  In the persistent @makeitmanifest workspace, run `python3 scripts/run_pipeline.py --date today --resume`.
  The supervisor owns state, gates, retries, and publishing.
  Do not restate or reinterpret the workflow.
  Return only: run ID, completed/scheduled/quarantined/blocked counts, blockers, and next action.

Created: [setup phase]
Enabled: yes
```

## Important Notes

### Cron Expression Syntax

The Routine cron expressions are interpreted in the **Routine's configured timezone** (not the server's UTC). When you set `cron_expression: "0 5 * * *"` on a Routine that targets `Europe/London`, it fires at 05:00 London time, converting to whatever UTC offset is currently in effect.

**Do NOT pre-convert to UTC.** The Routine system handles the conversion.

### Timezone Changes (DST Transitions)

No manual re-configuration is needed at daylight-saving transitions. The Routine system automatically accounts for the current offset at firing time.

### Verification

To verify the current schedule:

```bash
python3 -c "
from zoneinfo import ZoneInfo
from datetime import datetime

tz = ZoneInfo('Europe/London')
now = datetime.now(tz)
print(f'Local time: {now}')
print(f'UTC offset: {now.strftime(\"%z\")}')
print(f'DST active: {\"yes\" if now.dst() else \"no\"}')
"
```

### Multiple Firings on Same Day

If the scheduler misfires or a Routine runs multiple times in one calendar day (due to a retry, an early/late corrected time, etc.), both analytics and content jobs can run multiple times — that's OK. The state management in `run_analytics.py` and `run_pipeline.py` uses run IDs and date-based deduplication to ensure duplicate runs append findings/progress safely rather than overwriting each other.

## Setup Checklist

- [ ] Confirm Europe/London is set in `config/channel.json.publishing_schedule.timezone`
- [ ] Confirm `config/runtime.json.scheduling` has `timezone: "Europe/London"`
- [ ] Create Routine 1 (Analytics) with cron `0 5 * * *` and the minimal launcher prompt
- [ ] Create Routine 2 (Content) with cron `0 6 * * *` and the minimal launcher prompt
- [ ] Verify one full cycle: wait for 05:00 → 06:00 local time and confirm both Routines fire in order
- [ ] Check that a DST transition (Mar/Oct) does not break the schedule — times should stay consistent in local time even as UTC offsets shift
- [ ] Disable or delete any old fixed-UTC cron jobs still in the system

## Fallback: Manual Execution

If the Routine system is unavailable, you can run the jobs manually in order:

```bash
# At 05:00 local time, run analytics:
python3 scripts/run_analytics.py --date today

# At 06:00 local time, run content:
python3 scripts/run_pipeline.py --date today --resume
```

Conversely, if you need to test the jobs outside the normal schedule, you can invoke them directly at any time with the `--date` flag.

## References

- `config/channel.json.publishing_schedule`: publishing schedule config
- `config/runtime.json.scheduling`: timezone and job-time config
- `scripts/run_analytics.py`: analytics job entry point
- `scripts/run_pipeline.py`: content job entry point
- YOUTUBE_AUTOMATION_REPLICATION_GUIDE.md section 4: scheduled automation policy

---

**Last reviewed:** 2026-08-08  
**Next review trigger:** at next DST transition (March/October)
