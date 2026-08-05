#!/usr/bin/env python3
"""Regenerate state/channel_playbook.md — the distilled, durable channel
knowledge base (owner direction, 2026-08-01, "Persistent Channel Knowledge
Base"). Run this as the last step of the Daily analytics cycle, after the
dated state/performance_notes.json entry is appended.

state/performance_notes.json remains the historical source of truth. This
script never edits/deletes anything there — it only *reads* it (plus
state/video_analytics.json and the queue files for current counts) and
writes a compact, current-state summary to state/channel_playbook.md.

Honesty rule enforced here structurally, not just by convention: every
section this script can't back with real data from those files is written
as an explicit "not yet populated" note — never a fabricated example
finding. As of 2026-08-01 (first run of this script), most of the new
fatigue/cadence/CTA sections fall into that bucket, because no cycle has
run under the new structured protocol yet; only what's genuinely already
in state/performance_notes.json's cycles[] entries is surfaced.

Usage:
  python3 scripts/update_channel_playbook.py
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analytics_intelligence as ai  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
PLAYBOOK_PATH = os.path.join(STATE, "channel_playbook.md")
MAX_CHANGE_LOG_ENTRIES = 20

NOT_YET_POPULATED = (
    "_Not yet populated — no analytics cycle has produced structured evidence for this "
    "section yet. This is not a gap in the generator; it means the underlying finding "
    "doesn't exist as real, traceable data yet. See `state/performance_notes.json` for "
    "the full historical record this playbook distills._"
)


def _load(name, default=None):
    path = os.path.join(STATE, name)
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def _read_existing_change_log():
    """Pull prior change-log lines out of the existing playbook file, if any,
    so regenerating doesn't lose history — capped at MAX_CHANGE_LOG_ENTRIES
    so the file doesn't grow forever (older entries stay in
    state/performance_notes.json regardless)."""
    if not os.path.exists(PLAYBOOK_PATH):
        return []
    with open(PLAYBOOK_PATH) as f:
        text = f.read()
    marker = "## Change Log\n"
    if marker not in text:
        return []
    tail = text.split(marker, 1)[1]
    lines = [l for l in tail.strip().splitlines() if l.strip().startswith("- ")]
    return lines


def _own_channel_findings(performance_notes):
    """Extract whatever real own-channel-performance findings already exist
    in performance_notes.json's cycles[] — these are informal prose from
    before the structured protocol (2026-08-01), still real data, just not
    yet in the new attribute_findings[] shape. Surfaced honestly as
    narrative-sourced, not re-labeled as structured evidence they aren't."""
    cycles = performance_notes.get("cycles", [])
    out = []
    for c in cycles:
        findings = c.get("findings")
        if not findings:
            continue
        out.append({
            "run_at": c.get("run_at"),
            "findings": findings,
            "scouting_guidance": c.get("scouting_guidance"),
        })
    return out


def build_playbook(now=None):
    now = now or datetime.now(timezone.utc)
    performance_notes = _load("performance_notes.json", {})
    video_analytics = _load("video_analytics.json", {"videos": []})
    short_queue = _load("short_form_queue.json", {"queue": []})
    long_queue = _load("long_form_queue.json", {"queue": []})
    posted_history = _load("posted_history.json", {"short_form": [], "long_form": []})

    joined = ai.join_video_attributes(video_analytics, short_queue, long_queue)
    # Real bug fixed 2026-08-05: exclude videos already uploaded but still
    # private/scheduled for a future publishAt (the pre-2026-08-04 weekly-
    # batch backlog) -- their near-zero view counts reflect not-yet-public
    # status, not real performance, and were silently diluting every
    # baseline below. See analytics_intelligence.is_live_video()'s docstring.
    joined_live = ai.filter_live_videos(joined, now=now)
    shorts = [v for v in joined_live if v.get("format") == "short"]
    longs = [v for v in joined_live if v.get("format") == "long"]
    short_baseline = ai.format_baseline(shorts, now=now)
    long_baseline = ai.format_baseline(longs, now=now)
    missing_attr_count = sum(1 for v in joined_live if v.get("missing_attributes"))

    cycles = performance_notes.get("cycles", [])
    latest_cycle = cycles[-1] if cycles else None
    own_channel_findings = _own_channel_findings(performance_notes)

    n_shorts_published = len(posted_history.get("short_form", []))
    n_long_published = len(posted_history.get("long_form", []))

    experiment_ledger = performance_notes.get("experiment_ledger", [])

    lines = []
    lines.append("# Make It Manifest Channel Playbook")
    lines.append("")
    lines.append(f"Last updated: {now.isoformat()}")
    generated_from = "no analytics cycle run yet"
    if latest_cycle:
        generated_from = latest_cycle.get("run_id") or latest_cycle.get("run_at") or "(unlabeled prior cycle entry)"
    lines.append(f"Generated from analytics runs: {generated_from} (plus {len(cycles)} total cycle entries in state/performance_notes.json)")
    lines.append("")
    lines.append(
        "_This file is a distilled operational summary, not the source of truth. "
        "`state/performance_notes.json` and `state/video_analytics.json` hold the full history "
        "and every underlying evidence entry — nothing here should be trusted over them, and "
        "nothing here is ever the only place a finding lives._"
    )
    lines.append("")

    lines.append("## Channel Positioning")
    lines.append("")
    lines.append(
        "Aspirational luxury / manifestation / future-self motivation, cinematic lifestyle imagery. "
        "Shorts (fast-cut, upbeat-not-aggressive audio) and long-form ambience/background video "
        "(slow, calm, ambient audio) are deliberately different registers — see "
        "`config/channel.json.brand_identity` and `short_form_style_guidance`/`long_form_style_guidance` "
        "for the current, authoritative statement of this; this section is a pointer, not a duplicate."
    )
    lines.append("")

    lines.append("## Current Data Limitations")
    lines.append("")
    has_scope = video_analytics.get("has_analytics_scope")
    lines.append(f"- Analytics scope this generation: `has_analytics_scope={has_scope}` (Data API views/likes/comments are always available regardless; retention/watch-time need the Analytics scope and have a processing lag even when granted).")
    lines.append("- Retention, CTR, impressions, watch-time, and traffic-source data are not claimed anywhere in this file — CTR/impressions have no API path at all; the others are only ever included when a cycle explicitly pulled them.")
    lines.append(f"- {missing_attr_count} of {len(joined_live)} genuinely-live published videos currently don't join back to their scouted creative attributes (missing `published_video_id` linkage in the queue) — findings below are necessarily blind to those videos' angle/sound/title-pattern. ({len(joined) - len(joined_live)} additional videos are already uploaded but still private/scheduled for a future date and are excluded entirely from this file's numbers, not just this count.)")
    lines.append("- No historical per-video snapshots exist yet, so all performance windows are recent-upload cohorts (current cumulative totals for recently-published videos), not true deltas — see `agents/0_orchestrator.md`'s Daily analytics cycle for the exact distinction.")
    lines.append(f"- Sample sizes are still small: {n_shorts_published} Shorts and {n_long_published} long-form videos published to date. Most findings below are `observation`/`early_signal`, not `repeated_pattern` or `strong_channel_pattern` — read every confidence label literally.")
    lines.append("")

    def baseline_line(label, b):
        return (
            f"- **{label}** — n={b['n']}, median views={b['median_views']}, "
            f"median age-normalized views/day={round(b['median_age_normalized_views'], 1) if b['median_age_normalized_views'] is not None else None}, "
            f"median likes/1000 views={round(b['median_likes_per_1000_views'], 2) if b['median_likes_per_1000_views'] is not None else None}, "
            f"median comments/1000 views={round(b['median_comments_per_1000_views'], 2) if b['median_comments_per_1000_views'] is not None else None}"
        )

    lines.append("## Strong Channel Patterns")
    lines.append("")
    lines.append("_None yet._ No finding has persisted across enough batches/dates/controlled variations to earn this tier — see `agents/0_orchestrator.md`'s evidence-level rules. Current same-format baselines, for reference:")
    lines.append(baseline_line("Shorts", short_baseline))
    lines.append(baseline_line("Long-form", long_baseline))
    lines.append("")

    lines.append("## Promising Patterns to Validate")
    lines.append("")
    if own_channel_findings:
        latest = own_channel_findings[-1]
        lines.append(f"From the most recent narrative analytics finding (`{latest['run_at']}`, pre-structured-protocol prose, not yet re-derived under the 2026-08-01 evidence-level system — treat as `early_signal` at most):")
        lines.append("")
        lines.append(f"> {latest.get('scouting_guidance', '(no scouting_guidance recorded)')}")
    else:
        lines.append(NOT_YET_POPULATED)
    lines.append("")

    lines.append("## Winning Short-Form Patterns")
    lines.append("")
    if own_channel_findings:
        top = own_channel_findings[-1]["findings"].get("top_performers") if isinstance(own_channel_findings[-1]["findings"], dict) else None
        if top:
            for t in top[:5]:
                title = t.get("title", "—")
                views = t.get("views")
                likes = t.get("likes")
                lines.append(f"- \"{title}\" — {views} views, {likes} likes (raw totals from `{own_channel_findings[-1]['run_at']}`; not yet age-normalized/baselined under the new protocol — treat as `observation`).")
        else:
            lines.append(NOT_YET_POPULATED)
    else:
        lines.append(NOT_YET_POPULATED)
    lines.append("")

    lines.append("## Winning Long-Form Patterns")
    lines.append("")
    lines.append(NOT_YET_POPULATED if long_baseline["n"] < 3 else f"Baseline established (n={long_baseline['n']}) but no specific attribute-level winner has reached `repeated_pattern` confidence yet.")
    lines.append("")

    lines.append("## Underperforming Patterns")
    lines.append("")
    if own_channel_findings:
        bottom = own_channel_findings[-1]["findings"].get("bottom_performers") if isinstance(own_channel_findings[-1]["findings"], dict) else None
        if bottom:
            for b in bottom[:5]:
                title = b.get("title", "—")
                views = b.get("views")
                likes = b.get("likes")
                lines.append(f"- \"{title}\" — {views} views, {likes} likes (raw totals from `{own_channel_findings[-1]['run_at']}`; `observation`-level, upload age not yet controlled for).")
        else:
            lines.append(NOT_YET_POPULATED)
    else:
        lines.append(NOT_YET_POPULATED)
    lines.append("")

    for section in ("Audience Fatigue and Cooldowns", "Proven or Promising Title Structures",
                     "Proven or Promising Hook Structures", "Visual Patterns", "Audio Patterns",
                     "Atmosphere and Setting Patterns", "Series Performance", "Upload Cadence Findings"):
        lines.append(f"## {section}")
        lines.append("")
        lines.append(NOT_YET_POPULATED)
        lines.append("")

    lines.append("## CTA Experiments")
    lines.append("")
    if experiment_ledger:
        cta_experiments = [e for e in experiment_ledger if str(e.get("experiment_id", "")).startswith("cta-")]
        if cta_experiments:
            for e in cta_experiments:
                lines.append(f"- `{e.get('experiment_id')}` — status: `{e.get('status')}`, hypothesis: {e.get('hypothesis', '—')}")
        else:
            lines.append(NOT_YET_POPULATED)
    else:
        import cta_experiment as cta  # local import: only needed for this section
        lines.append(f"Active experiment defined in code (`scripts/cta_experiment.py`): `{cta.CTA_LUXURY_EXPERIMENT_ID}`, control variant `{cta.DEFAULT_VARIANT_ID}` = `{cta.CTA_VARIANTS[cta.DEFAULT_VARIANT_ID]}`. No ledger entry or published-video results exist yet — this is infrastructure ready to collect evidence, not a finding.")
    lines.append("")

    lines.append("## Active Experiments")
    lines.append("")
    active = [e for e in experiment_ledger if e.get("status") in ("proposed", "scheduled", "published", "gathering_data", "promising")]
    if active:
        for e in active:
            lines.append(f"- `{e.get('experiment_id')}` — {e.get('status')} — {e.get('hypothesis', '—')}")
    else:
        lines.append(NOT_YET_POPULATED)
    lines.append("")

    for section, statuses in (
        ("Recently Confirmed Experiments", ("confirmed",)),
        ("Inconclusive Experiments", ("inconclusive",)),
        ("Rejected Experiments", ("rejected",)),
        ("Temporarily Retired Ideas", ("retired",)),
    ):
        lines.append(f"## {section}")
        lines.append("")
        matches = [e for e in experiment_ledger if e.get("status") in statuses]
        if matches:
            for e in matches:
                lines.append(f"- `{e.get('experiment_id')}` — {e.get('result', e.get('hypothesis', '—'))}")
        else:
            lines.append(NOT_YET_POPULATED)
        lines.append("")

    lines.append("## Exploration Priorities")
    lines.append("")
    lines.append(NOT_YET_POPULATED)
    lines.append("")

    lines.append("## Instructions for the Next Scouting Run")
    lines.append("")
    if latest_cycle and latest_cycle.get("instructions_for_next_scouting_run"):
        for instr in latest_cycle["instructions_for_next_scouting_run"]:
            lines.append(f"- {instr}")
    elif own_channel_findings:
        lines.append(f"> {own_channel_findings[-1].get('scouting_guidance', '(none recorded)')}")
    else:
        lines.append(NOT_YET_POPULATED)
    lines.append("")

    lines.append("## Contradictions and Uncertainties")
    lines.append("")
    lines.append(NOT_YET_POPULATED)
    lines.append("")

    lines.append("## Change Log")
    lines.append("")
    existing_log = _read_existing_change_log()
    new_entry = f"- {now.isoformat()}: regenerated from {len(cycles)} cycle entries, {len(joined_live)} live joined videos ({missing_attr_count} missing attributes, {len(joined) - len(joined_live)} future-scheduled excluded), {len(experiment_ledger)} ledger experiments."
    combined_log = ([new_entry] + existing_log)[:MAX_CHANGE_LOG_ENTRIES]
    lines.extend(combined_log)
    lines.append("")

    return "\n".join(lines)


def write_playbook(now=None):
    """Atomic write: build the full new content in memory, write to a temp
    file, then os.replace() into place — a crash/error mid-write can never
    leave a partially-written or corrupted playbook, and a failed run never
    destroys the previous valid version (the temp file just doesn't get
    renamed over it)."""
    content = build_playbook(now=now)
    tmp_path = PLAYBOOK_PATH + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)
    os.replace(tmp_path, PLAYBOOK_PATH)
    return PLAYBOOK_PATH


if __name__ == "__main__":
    path = write_playbook()
    print(f"wrote {path}")
