#!/usr/bin/env python3
"""Reusable math/plumbing for the Daily analytics cycle's Analytics
Intelligence and Self-Improvement Protocol (owner direction, 2026-08-01) —
see agents/0_orchestrator.md's "Daily analytics cycle" section for the full
protocol this supports.

This module deliberately does NOT decide what a finding *means* — no
"luxury videos work" style conclusions are generated here. It only provides
the deterministic, explainable building blocks (safe rate math, age
normalization, per-format medians, evidence-level suggestions, the
attribute join, and a safe append helper for state/performance_notes.json)
that the orchestrator uses while forming and recording those conclusions
itself. Interpretation — what's a real pattern vs. a coincidence, what to
repeat/vary/reduce/retire — stays a judgment call made when the cycle runs,
not something this script automates away.

No new metrics are invented here: only views/likes/comments (the fields
scripts/pull_video_analytics.py's Data API path actually returns) are used.
Retention/CTR/impressions/watch-time/traffic-source data is never touched.
"""
import json
import os
import statistics
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")

# Evidence-level thresholds (guidance, not proof — see module docstring and
# agents/0_orchestrator.md: sample *quality*, not just count, still matters).
EVIDENCE_LEVELS = {
    1: "observation",
    2: "early_signal",
    3: "repeated_pattern",
}
# "strong_channel_pattern" requires persistence across multiple batches/dates,
# which this module cannot judge from a single run — that upgrade is always
# a manual call the orchestrator makes by reading prior cycle entries, never
# assigned automatically here.


def safe_div(numerator, denominator):
    """Division that returns None instead of raising/producing garbage on a
    zero or missing denominator — every rate below routes through this so a
    zero-view video never silently becomes a divide-by-zero crash or an
    infinite/misleading rate."""
    if not denominator:
        return None
    return numerator / denominator


def rate_per_1000(count, views):
    """e.g. likes_per_1000_views, comments_per_1000_views. None if views is
    falsy/zero — never fabricate a rate off zero views."""
    if count is None or views is None:
        return None
    r = safe_div(count, views)
    return None if r is None else r * 1000.0


def age_days(published_at, now=None):
    """Days since publish, as a float. Returns None if published_at is
    missing/unparseable. Clamped to a small positive floor (0.05 days, ~72
    minutes) rather than 0, so a just-published video's age-normalized
    views doesn't divide by (near) zero and produce an absurd spike."""
    if not published_at:
        return None
    try:
        pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    now = now or datetime.now(timezone.utc)
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    delta = (now - pub).total_seconds() / 86400.0
    return max(delta, 0.05)


def age_normalized_views(views, published_at, now=None):
    """views / days_since_publish. None if either input is unusable. This
    is a recent-upload-cohort normalization, not a true 7-day delta — it
    does not require historical snapshots, but it also doesn't produce one;
    label it as such wherever it's surfaced (see the orchestrator doc's
    data_quality.window_type field)."""
    if views is None:
        return None
    a = age_days(published_at, now)
    if a is None:
        return None
    return views / a


def median(values):
    """Median of non-None values; None if the list is empty after filtering.
    Prefer this over mean everywhere a single viral outlier could distort
    the result — see agents/0_orchestrator.md's data-quality rules."""
    clean = [v for v in values if v is not None]
    if not clean:
        return None
    return statistics.median(clean)


def format_baseline(videos, now=None):
    """Given a list of video dicts (each with at least views/likes/comments/
    published_at), return the median views, age-normalized views, like-rate,
    and comment-rate for that group — the same-format baseline every
    individual video should be compared against, never against the other
    format. Also returns n (sample size) so callers can label thin samples
    honestly."""
    views_list = [v.get("views") for v in videos]
    age_norm_list = [age_normalized_views(v.get("views"), v.get("published_at"), now) for v in videos]
    like_rate_list = [rate_per_1000(v.get("likes"), v.get("views")) for v in videos]
    comment_rate_list = [rate_per_1000(v.get("comments"), v.get("views")) for v in videos]
    return {
        "n": len(videos),
        "median_views": median(views_list),
        "median_age_normalized_views": median(age_norm_list),
        "median_likes_per_1000_views": median(like_rate_list),
        "median_comments_per_1000_views": median(comment_rate_list),
    }


def classify_evidence_level(comparable_sample_count):
    """Suggested evidence level from a raw comparable-sample count alone.
    This is a floor/starting suggestion, not a verdict — the orchestrator
    must still down-rate it if the samples aren't genuinely comparable
    (different formats, wildly different ages, a single outlier dominating
    the average). Never auto-upgrades to strong_channel_pattern; that tier
    requires persistence across batches/dates, a judgment only a human-in-
    the-loop-style read of prior cycle entries can make."""
    if comparable_sample_count <= 0:
        return None
    return EVIDENCE_LEVELS.get(comparable_sample_count, "repeated_pattern")


def join_video_attributes(video_analytics, short_queue, long_queue):
    """Join state/video_analytics.json's per-video stats (views/likes/
    comments/published_at) with the creative attributes already captured at
    scouting time in state/short_form_queue.json / state/long_form_queue.json
    (angle, title_pattern/title, trending_sound_style/sound_direction),
    via each queue entry's published_video_id field.

    Returns a list of merged dicts. Does not invent any attribute field
    that doesn't already exist in the queue schemas — if an attribute is
    missing on a given candidate, its key is simply absent (or None) here,
    which callers should surface as a data-quality gap, not paper over.
    """
    by_video_id = {}
    for entry in short_queue.get("queue", []):
        vid = entry.get("published_video_id")
        if vid:
            by_video_id[vid] = {
                "candidate_id": entry.get("id"),
                "angle": entry.get("angle"),
                "title_pattern": entry.get("title_pattern") or entry.get("title"),
                "sound_style": entry.get("trending_sound_style") or entry.get("sound_direction"),
            }
    for entry in long_queue.get("queue", []):
        vid = entry.get("published_video_id")
        if vid:
            by_video_id[vid] = {
                "candidate_id": entry.get("id"),
                "angle": entry.get("visual_theme") or entry.get("angle"),
                "title_pattern": entry.get("title"),
                "sound_style": entry.get("mood"),
            }

    joined = []
    for v in video_analytics.get("videos", []):
        attrs = by_video_id.get(v["video_id"], {})
        merged = dict(v)
        merged["candidate_id"] = attrs.get("candidate_id")
        merged["angle"] = attrs.get("angle")
        merged["title_pattern"] = attrs.get("title_pattern")
        merged["sound_style"] = attrs.get("sound_style")
        merged["missing_attributes"] = [
            k for k in ("candidate_id", "angle", "title_pattern", "sound_style") if not attrs.get(k)
        ]
        joined.append(merged)
    return joined


def make_run_id(now=None):
    """analytics-YYYY-MM-DD-HHMM — unique per firing (not just per date), so
    a same-day re-run never silently collides with/overwrites an earlier
    run's entry. Callers append a new entry with this id; nothing already
    in state/performance_notes.json is ever edited or removed."""
    now = now or datetime.now(timezone.utc)
    return f"analytics-{now.strftime('%Y-%m-%d-%H%M')}"


def append_performance_notes_cycle(entry, path=None):
    """Append one dated entry to state/performance_notes.json's existing
    `cycles` array — never overwrites/removes any prior entry, never
    replaces the file's other top-level keys (competitor_scan_* entries
    etc.). Re-reads and validates the file after writing, same discipline
    every other publish-adjacent script in this project already follows
    (see e.g. agents/short_form/4.1_publisher.md's re-read-and-confirm
    step) — a bad write here should fail loudly, not silently corrupt the
    channel's only persistent memory of what's already been tried.
    """
    path = path or os.path.join(STATE, "performance_notes.json")
    with open(path) as f:
        notes = json.load(f)

    notes.setdefault("cycles", [])
    existing_ids = {c.get("run_id") for c in notes["cycles"] if c.get("run_id")}
    if entry.get("run_id") in existing_ids:
        raise ValueError(
            f"run_id {entry.get('run_id')!r} already present in state/performance_notes.json — "
            f"refusing to append a duplicate; generate a fresh run_id via make_run_id()."
        )
    notes["cycles"].append(entry)

    tmp_path = path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(notes, f, indent=2)
    os.replace(tmp_path, path)

    with open(path) as f:
        reread = json.load(f)
    if reread["cycles"][-1].get("run_id") != entry.get("run_id"):
        raise RuntimeError("post-write verification failed: appended entry not found at end of cycles[]")
    return len(reread["cycles"])
