#!/usr/bin/env python3
"""Reusable math/plumbing for the Daily analytics cycle's Analytics
Intelligence and Self-Improvement Protocol (owner direction, 2026-08-01) —
see agents/0_orchestrator.md's "Daily analytics cycle" section for the full
protocol this supports.

This module deliberately does NOT decide what a finding *means* — no
"luxury videos work" style conclusions are generated here. It only provides
the deterministic, explainable building blocks (safe rate math, age
normalization, per-format medians, evidence-level suggestions, the
attribute join, cadence/timezone math, fatigue-classification thresholds,
and a safe append helper for state/performance_notes.json) that the
orchestrator uses while forming and recording those conclusions itself.
Interpretation — what's a real pattern vs. a coincidence, what to
repeat/vary/reduce/retire — stays a judgment call made when the cycle runs,
not something this script automates away.

No new metrics are invented here: only views/likes/comments (the fields
scripts/pull_video_analytics.py's Data API path actually returns) are used.
Retention/CTR/impressions/watch-time/traffic-source data is never touched.

Extended 2026-08-01 (owner direction) with audience-fatigue detection and
upload-cadence helpers, as part of the same closed learning loop — see
`fatigue_assessment()` and `local_time_info()`/`time_block()` below. Pattern
*matching* (deciding which recent videos share a "pattern" worth tracking
fatigue on) is a judgment call the orchestrator makes by reading `angle`/
`sound_style`/etc. text, since those are free-text fields, not structured
tags this module can auto-cluster reliably — this module only does the
frequency/trend/threshold math once the caller supplies which videos belong
to a pattern.
"""
import hashlib
import json
import os
import statistics
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

CHANNEL_TIMEZONE = "Europe/London"  # matches config/channel.json.publishing_schedule.timezone

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


def is_live_video(v, now=None):
    """True only if this video's published_at is a real, past timestamp --
    i.e. it has actually gone public. Real bug found 2026-08-05 (analytics
    cycle diagnosis): state/video_analytics.json can contain videos already
    uploaded via the API but still privacyStatus=private with a future
    publishAt (the pre-2026-08-04 weekly-batch backlog, scheduled for days
    still to come). Their view counts are near-zero because nobody has been
    able to watch them yet, not because they underperformed -- age_days()'s
    own floor clamp (0.05 days) means a future-dated video doesn't error
    out, it just silently produces a small-but-nonzero age_normalized_views
    figure that looks like real (bad) performance data if it's mixed into a
    baseline. Every baseline/finding that judges *performance* must filter
    to is_live_video() first; a caller that specifically wants to know what
    unpublished/scheduled inventory exists should say so explicitly rather
    than silently including it in a performance number."""
    published_at = v.get("published_at")
    if not published_at:
        return False
    try:
        pub = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    now = now or datetime.now(timezone.utc)
    if pub.tzinfo is None:
        pub = pub.replace(tzinfo=timezone.utc)
    return pub <= now


def filter_live_videos(videos, now=None):
    """videos filtered to is_live_video() only -- see its docstring. Use
    this before format_baseline()/fatigue_assessment()/group_baseline_by_key()
    whenever the caller is judging real performance, not just enumerating
    inventory."""
    return [v for v in videos if is_live_video(v, now)]


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


# ---------------------------------------------------------------------------
# Upload cadence (owner direction, 2026-08-01)
# ---------------------------------------------------------------------------

def local_time_info(published_at, tz_name=CHANNEL_TIMEZONE):
    """Convert a UTC ISO timestamp to timezone-aware local publication info.

    Uses zoneinfo (IANA tz database), not a fixed offset — this correctly
    handles the BST/GMT transition across the year rather than assuming a
    single +00:00/+01:00 offset for every date. Returns None if
    published_at is missing/unparseable, never a fabricated guess.
    """
    if not published_at:
        return None
    try:
        utc_dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    if utc_dt.tzinfo is None:
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
    local_dt = utc_dt.astimezone(ZoneInfo(tz_name))
    return {
        "utc_iso": utc_dt.isoformat(),
        "local_iso": local_dt.isoformat(),
        "timezone": tz_name,
        "weekday": local_dt.strftime("%A"),
        "is_weekend": local_dt.weekday() >= 5,
        "hour": local_dt.hour,
        "time_block": time_block(local_dt.hour),
    }


def time_block(hour):
    """Local-hour groupings (see agents/0_orchestrator.md's Daily analytics
    cycle) — used only as a broader bucket when per-hour samples are too
    thin; exact hour is always retained alongside this in local_time_info()."""
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "late_night"  # 22:00-05:59


def hours_between(earlier_iso, later_iso):
    """Hours between two ISO timestamps (later - earlier). None if either is
    missing/unparseable. Used for upload-spacing analysis (time since the
    previous same-format upload, time since any previous upload)."""
    if not earlier_iso or not later_iso:
        return None
    try:
        a = datetime.fromisoformat(earlier_iso.replace("Z", "+00:00"))
        b = datetime.fromisoformat(later_iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (b - a).total_seconds() / 3600.0


def cadence_features(video, previous_same_format=None, previous_any_format=None, tz_name=CHANNEL_TIMEZONE):
    """Build the cadence feature set for one published video (see
    agents/0_orchestrator.md's Daily analytics cycle, "Data to Record"):
    local weekday/hour/time_block, hours since the previous same-format
    upload, hours since any previous upload. `previous_same_format`/
    `previous_any_format` are the immediately-preceding video dicts (or
    None if this is the first of their kind) — the caller supplies these
    since "previous" depends on the full sorted publish history, which this
    function doesn't own.
    """
    info = local_time_info(video.get("published_at"), tz_name)
    return {
        "video_id": video.get("video_id"),
        "format": video.get("format"),
        "local_time": info,
        "hours_since_previous_same_format": hours_between(
            (previous_same_format or {}).get("published_at"), video.get("published_at")
        ) if previous_same_format else None,
        "hours_since_previous_any_format": hours_between(
            (previous_any_format or {}).get("published_at"), video.get("published_at")
        ) if previous_any_format else None,
    }


def group_baseline_by_key(videos, key_fn, now=None):
    """format_baseline(), grouped by an arbitrary key function (e.g. time
    block, weekday) — returns {key: baseline_dict}. Groups with too few
    videos still get a baseline (n reflects that honestly); it's on the
    caller to avoid over-claiming a conclusion from a thin group, same
    discipline as everywhere else in this module."""
    groups = {}
    for v in videos:
        groups.setdefault(key_fn(v), []).append(v)
    return {k: format_baseline(vs, now=now) for k, vs in groups.items()}


# ---------------------------------------------------------------------------
# Audience fatigue detection (owner direction, 2026-08-01)
# ---------------------------------------------------------------------------

# Default guidance thresholds — cautious starting rules, not absolute truth
# (see agents/0_orchestrator.md). A future project-specific override should
# live in config, not require editing this module.
FATIGUE_SHARE_THRESHOLD = 0.30       # >30% of the last 10 same-format uploads
FATIGUE_CONSECUTIVE_THRESHOLD = 3    # 3+ consecutive same-format uploads


def fatigue_assessment(pattern_videos_recent_first, same_format_recent_first, baseline, now=None):
    """Assess one creative pattern's fatigue status.

    Args:
      pattern_videos_recent_first: videos matching this pattern, most-recent
        first, in the same order they appear within same_format_recent_first
        (a subsequence of it) — this is what "the pattern" means operationally:
        whichever videos the caller has judged to share the mechanism being
        evaluated. This function does not itself decide pattern membership.
      same_format_recent_first: ALL recent videos of the same format
        (short or long, never mixed), most-recent first — used to compute
        share-of-recent-slots and consecutive-use counts.
      baseline: the same-format baseline dict from format_baseline(), i.e.
        what "the median" for this format currently is — pattern videos are
        judged against this, never against the other format.
      now: for age-normalization; defaults to current time.

    Returns a dict with recent_usage counts, a performance_trend
    ("declining"/"stable"/"improving"/"insufficient_data"), a
    fatigue_status, a confidence-style note, and — deliberately — no single
    opaque score. Classification logic mirrors the default guidance:
    fatigue requires BOTH substantial repetition AND weakening performance;
    frequency alone (strong performance, high repetition) is `diversify`,
    never `reduce`/`retire_temporarily` on its own.
    """
    last_10 = same_format_recent_first[:10]
    last_20 = same_format_recent_first[:20]
    pattern_ids = {v.get("video_id") for v in pattern_videos_recent_first}

    last_10_count = sum(1 for v in last_10 if v.get("video_id") in pattern_ids)
    last_20_count = sum(1 for v in last_20 if v.get("video_id") in pattern_ids)

    consecutive = 0
    for v in same_format_recent_first:
        if v.get("video_id") in pattern_ids:
            consecutive += 1
        else:
            break

    share_of_last_10 = safe_div(last_10_count, len(last_10)) if last_10 else None

    # Performance trend: compare the pattern's most recent use(s) against
    # its own earlier use(s), each side normalized by age — never against
    # a raw total, and never with fewer than 2 uses on a side.
    trend = "insufficient_data"
    if len(pattern_videos_recent_first) >= 4:
        half = len(pattern_videos_recent_first) // 2
        recent_half = pattern_videos_recent_first[:half]
        older_half = pattern_videos_recent_first[half:]
        recent_median = median([age_normalized_views(v.get("views"), v.get("published_at"), now) for v in recent_half])
        older_median = median([age_normalized_views(v.get("views"), v.get("published_at"), now) for v in older_half])
        if recent_median is not None and older_median is not None and older_median > 0:
            ratio = recent_median / older_median
            if ratio < 0.85:
                trend = "declining"
            elif ratio > 1.15:
                trend = "improving"
            else:
                trend = "stable"
    elif len(pattern_videos_recent_first) >= 2:
        trend = "insufficient_data"  # too few uses to trust a within-pattern trend split

    pattern_median_age_norm = median([
        age_normalized_views(v.get("views"), v.get("published_at"), now) for v in pattern_videos_recent_first
    ])
    above_baseline = (
        pattern_median_age_norm is not None
        and baseline.get("median_age_normalized_views") is not None
        and pattern_median_age_norm >= baseline["median_age_normalized_views"]
    )

    high_repetition = (
        (share_of_last_10 is not None and share_of_last_10 > FATIGUE_SHARE_THRESHOLD)
        or consecutive >= FATIGUE_CONSECUTIVE_THRESHOLD
    )
    weakening = trend == "declining"

    if len(pattern_videos_recent_first) <= 1:
        status = "healthy"
        reason = "Only one use so far — not enough repetition to assess fatigue at all."
    elif high_repetition and weakening:
        status = "fatigue_detected"
        reason = (
            f"High recent repetition ({last_10_count}/{len(last_10)} of last 10 same-format uploads, "
            f"{consecutive} consecutive) combined with a declining performance trend."
        )
    elif high_repetition and above_baseline and not weakening:
        status = "diversify"
        reason = (
            f"Repetition is high ({last_10_count}/{len(last_10)} of last 10 same-format uploads) but "
            f"performance remains at/above the same-format baseline — preserve the mechanism, vary the execution."
        )
    elif high_repetition:
        status = "diversify"
        reason = "Repetition is high; performance trend is not clearly declining, but not confirmed strong either — diversify as a precaution rather than reduce."
    elif weakening:
        status = "repeat_carefully"
        reason = "Performance trend is declining but repetition is not yet high — one more comparable use, watched closely, before any reduction."
    else:
        status = "healthy"
        reason = "Neither repetition nor performance trend currently indicate a fatigue concern."

    return {
        "recent_usage": {
            "last_10_same_format": last_10_count,
            "last_20_same_format": last_20_count,
            "consecutive_uses": consecutive,
            "share_of_last_10": share_of_last_10,
        },
        "performance_trend": trend,
        "above_same_format_baseline": above_baseline,
        "fatigue_status": status,
        "reason": reason,
        "sample_size": len(pattern_videos_recent_first),
    }


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


# ---------------------------------------------------------------------------
# Growth trajectory toward the subscriber objective (owner direction, 2026-08-02)
# ---------------------------------------------------------------------------

def _parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _pace_over_window(subscribers_daily_series, window_days, now=None):
    """Net subscriber gain per day, averaged over the most recent
    window_days of ACTUAL available data (never fabricated) — returns
    (pace_per_day, days_of_data_used). Real daily data (state/video_analytics
    .json's subscribers_daily_series, from a dimensions="day" Analytics API
    query) is sparse on a very new channel and often lags a day or two
    behind the current date — this only ever averages over days that
    genuinely have a row, and reports how many that was, so a caller never
    presents a 2-day average as if it were a real 7-day trend."""
    if not subscribers_daily_series:
        return None, 0
    sorted_series = sorted(subscribers_daily_series, key=lambda r: r["date"])
    window = sorted_series[-window_days:]
    if not window:
        return None, 0
    total_net = sum(r.get("net", r.get("subscribers_gained", 0) - r.get("subscribers_lost", 0)) for r in window)
    days = len(window)
    return (total_net / days if days else None), days


def next_checkpoint(current_subscribers, checkpoints, now=None):
    """The first checkpoint (from config/growth_strategy.json's
    `checkpoints` list) whose date is still in the future — regardless of
    whether current_subscribers has already reached it (a checkpoint is a
    pacing marker for a DATE, not just a subscriber count; being ahead of
    an earlier checkpoint doesn't retroactively change which one is
    "next"). Returns None if every checkpoint's date has passed."""
    now = now or datetime.now(timezone.utc)
    future = [c for c in checkpoints if _parse_date(c["date"]) >= now]
    if not future:
        return None
    return min(future, key=lambda c: c["date"])


def calculate_trajectory(current_subscribers, subscribers_daily_series, growth_config, now=None):
    """The full growth-trajectory snapshot toward growth_config's
    objective.target_subscribers by objective.target_date — every number
    here is either a direct real input or simple arithmetic on real
    inputs, nothing estimated or invented. Returns a dict; see inline keys.

    data_confidence is deliberately blunt (very_low/low/moderate/high based
    on how many real days of subscriber data are actually available) so a
    caller can't accidentally treat a 3-day average as a reliable channel
    trend — on a brand-new channel this will read very_low for weeks, and
    that's the honest answer, not a bug to work around.
    """
    now = now or datetime.now(timezone.utc)
    obj = growth_config["objective"]
    target_subscribers = obj["target_subscribers"]
    target_date = _parse_date(obj["target_date"])
    checkpoints = growth_config["checkpoints"]
    thresholds = growth_config["trajectory_status_thresholds"]

    remaining_subscribers = max(target_subscribers - current_subscribers, 0)
    remaining_days = max((target_date - now).days, 0)
    required_daily_pace = safe_div(remaining_subscribers, remaining_days) if remaining_days else None
    required_weekly_pace = required_daily_pace * 7 if required_daily_pace is not None else None

    pace_7day, days_7 = _pace_over_window(subscribers_daily_series, 7, now)
    pace_28day, days_28 = _pace_over_window(subscribers_daily_series, 28, now)

    if days_7 >= 7:
        data_confidence = "moderate"
    elif days_7 >= 3:
        data_confidence = "low"
    elif days_7 >= 1:
        data_confidence = "very_low"
    else:
        data_confidence = "no_data"

    projection_7day = current_subscribers + pace_7day * remaining_days if pace_7day is not None else None
    projection_28day = current_subscribers + pace_28day * remaining_days if pace_28day is not None else None

    pct_complete = safe_div(current_subscribers, target_subscribers) * 100 if target_subscribers else None

    nc = next_checkpoint(current_subscribers, checkpoints, now)
    checkpoint_status = None
    if nc:
        days_to_checkpoint = max((_parse_date(nc["date"]) - now).days, 0)
        subs_needed_for_checkpoint = max(nc["subscribers"] - current_subscribers, 0)
        required_pace_to_checkpoint = safe_div(subs_needed_for_checkpoint, days_to_checkpoint) if days_to_checkpoint else None

        best_pace = pace_7day if pace_7day is not None else pace_28day
        if best_pace is None or required_pace_to_checkpoint is None or data_confidence == "no_data":
            checkpoint_status = "insufficient_data"
        else:
            pct_of_required = safe_div(best_pace, required_pace_to_checkpoint) * 100 if required_pace_to_checkpoint else (100.0 if subs_needed_for_checkpoint == 0 else 0.0)
            if pct_of_required >= thresholds["green_min_pct_of_required_pace"]:
                checkpoint_status = "GREEN"
            elif pct_of_required >= thresholds["amber_min_pct_of_required_pace"]:
                checkpoint_status = "AMBER"
            else:
                checkpoint_status = "RED"

    return {
        "current_subscribers": current_subscribers,
        "target_subscribers": target_subscribers,
        "target_date": obj["target_date"],
        "remaining_subscribers": remaining_subscribers,
        "remaining_days": remaining_days,
        "required_daily_pace": required_daily_pace,
        "required_weekly_pace": required_weekly_pace,
        "pace_7day_subscribers_per_day": pace_7day,
        "pace_7day_days_of_data": days_7,
        "pace_28day_subscribers_per_day": pace_28day,
        "pace_28day_days_of_data": days_28,
        "data_confidence": data_confidence,
        "projected_subscribers_at_target_date_7day_pace": projection_7day,
        "projected_subscribers_at_target_date_28day_pace": projection_28day,
        "percent_of_target_complete": pct_complete,
        "next_checkpoint": nc,
        "trajectory_status": checkpoint_status,
        "note": "A stretch objective, not a guaranteed forecast. Pace/projection figures are arithmetic on real subscribers_daily_series data only (state/video_analytics.json, via the YouTube Analytics API's dimensions=day query) — never estimated. On a very new channel, data_confidence will genuinely be very_low/no_data for some time; treat any status derived from it as low-confidence, not a verdict.",
    }
