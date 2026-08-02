#!/usr/bin/env python3
"""
Real, structured tracking of short-form raw-clip usage — replaces the old
"prefer a genuine visual fit over avoiding reuse, check other candidates'
transform_log entries" soft/manual instruction (owner-reported real bug,
2026-08-02: raw/68.mp4 and raw/65.mp4 were each reused across 3 published
Shorts IN A ROW — sf_022, sf_023, sf_024 — because nothing actually enforced
the "not in the immediately preceding 5" rule, it just relied on an agent
reading free-text prose and remembering).

Going forward, Agent 3.1 (short-form producer) writes a structured
`clips_used` list (e.g. ["9", "19", "29"]) on each candidate's
state/short_form_queue.json entry, alongside the existing free-text
`transform_log`. This module reads that field when present, and falls back
to regex-parsing transform_log's prose for older candidates that predate
the structured field (never invents usage that isn't actually recorded
somewhere).

Usage:
    python3 clip_pool_status.py                 # full report
    python3 clip_pool_status.py --cooldown-only  # just the last-5 cooldown set
"""
import argparse
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
RAW_CLIPS_DIR = os.path.join(ROOT, "assets", "short-form-clips", "raw")

DEFAULT_LOOKBACK = 5

_TRANSFORM_LOG_CLIPS_RE = re.compile(r"\(raw/([\d,]+)\.mp4")


def pool_size(raw_clips_dir=None):
    """Count of actual .mp4 files in the raw clip pool — the real ceiling,
    not a number copied from documentation that can go stale."""
    d = raw_clips_dir or RAW_CLIPS_DIR
    if not os.path.isdir(d):
        return 0
    return len([f for f in os.listdir(d) if f.endswith(".mp4")])


def clips_used_for_candidate(candidate):
    """The list of raw clip IDs (as strings, e.g. "9") actually used by this
    candidate. Prefers the structured `clips_used` field; falls back to
    parsing `transform_log`'s prose for older candidates that predate the
    structured field. Returns [] if neither source yields anything —
    never guesses."""
    structured = candidate.get("clips_used")
    if isinstance(structured, list) and structured:
        return [str(c) for c in structured]

    tl = candidate.get("transform_log", "")
    if isinstance(tl, list):
        tl = " ".join(str(x) for x in tl)
    if not isinstance(tl, str):
        return []
    m = _TRANSFORM_LOG_CLIPS_RE.search(tl)
    if not m:
        return []
    return m.group(1).split(",")


def _sort_key(candidate):
    return candidate.get("published_at") or candidate.get("produced_at") or candidate.get("scripted_at") or ""


def published_candidates_recent_first(queue):
    """Published short-form candidates, most recent first, using the best
    available real timestamp (published_at, falling back to produced_at)."""
    published = [c for c in queue.get("queue", []) if c.get("status") == "published"]
    return sorted(published, key=_sort_key, reverse=True)


def recently_used_clips(queue, lookback=DEFAULT_LOOKBACK):
    """The real cooldown set: every raw clip ID used in any of the most
    recent `lookback` PUBLISHED short-form candidates. This is the hard
    no-reuse set a new candidate's clip selection must avoid (see
    agents/short_form/3.1_producer.md) unless the pool is genuinely
    exhausted for the candidate's visual_direction, which must then be
    stated explicitly rather than silently defaulting into a repeat."""
    recent = published_candidates_recent_first(queue)[:lookback]
    cooldown = set()
    for c in recent:
        cooldown.update(clips_used_for_candidate(c))
    return cooldown, recent


def usage_report(queue, raw_clips_dir=None, lookback=DEFAULT_LOOKBACK):
    """Full usage report: per-clip usage counts across every published
    candidate with resolvable clip data, which clips have never been used,
    the current cooldown set, and any real back-to-back-reuse violations
    found in the actual publish history (informational — this reports on
    history, it doesn't retroactively fix it)."""
    counter = Counter()
    unresolved_candidates = []
    for c in queue.get("queue", []):
        if c.get("status") != "published":
            continue
        clips = clips_used_for_candidate(c)
        if not clips:
            unresolved_candidates.append(c.get("id"))
            continue
        for clip in clips:
            counter[clip] += 1

    size = pool_size(raw_clips_dir)
    all_clip_ids = {str(i) for i in range(1, size + 1)} if size else set(counter)
    never_used = sorted(all_clip_ids - set(counter), key=lambda x: int(x) if x.isdigit() else 0)

    cooldown, recent = recently_used_clips(queue, lookback)

    # Violations: a clip appearing in 2+ of the most recent `lookback`
    # candidates — the exact failure mode this module exists to catch.
    recent_counts = Counter()
    for c in recent:
        for clip in clips_used_for_candidate(c):
            recent_counts[clip] += 1
    violations = {clip: n for clip, n in recent_counts.items() if n > 1}

    return {
        "pool_size": size,
        "resolved_candidate_count": sum(1 for c in queue.get("queue", []) if c.get("status") == "published") - len(unresolved_candidates),
        "unresolved_candidates": unresolved_candidates,
        "usage_counts": dict(counter.most_common()),
        "never_used_clips": never_used,
        "cooldown_lookback": lookback,
        "cooldown_set": sorted(cooldown, key=lambda x: int(x) if x.isdigit() else 0),
        "cooldown_candidates": [c.get("id") for c in recent],
        "recent_window_violations": violations,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback", type=int, default=DEFAULT_LOOKBACK)
    parser.add_argument("--cooldown-only", action="store_true", help="Print just the cooldown set (for quick pre-selection checks)")
    parser.add_argument("--queue-path", default=os.path.join(STATE, "short_form_queue.json"))
    args = parser.parse_args()

    queue = json.load(open(args.queue_path))

    if args.cooldown_only:
        cooldown, recent = recently_used_clips(queue, args.lookback)
        print(f"COOLDOWN_SET (last {args.lookback} published: {[c.get('id') for c in recent]}):")
        print(sorted(cooldown, key=lambda x: int(x) if x.isdigit() else 0))
    else:
        report = usage_report(queue, lookback=args.lookback)
        print(f"Raw clip pool size: {report['pool_size']}")
        print(f"Published candidates with resolvable clip data: {report['resolved_candidate_count']}")
        if report["unresolved_candidates"]:
            print(f"Unresolved (no clips_used field, no parseable transform_log): {report['unresolved_candidates']}")
        print()
        print(f"Cooldown set (must avoid, last {report['cooldown_lookback']} published: {report['cooldown_candidates']}):")
        print(f"  {report['cooldown_set']}")
        if report["recent_window_violations"]:
            print()
            print(f"REAL VIOLATIONS in the last {report['cooldown_lookback']} published candidates (clip reused within the cooldown window):")
            for clip, n in sorted(report["recent_window_violations"].items(), key=lambda x: -x[1]):
                print(f"  raw/{clip}.mp4 used {n}x within the last {report['cooldown_lookback']} published Shorts")
        print()
        print("Usage counts (all published history, most-used first):")
        for clip, n in report["usage_counts"].items():
            print(f"  raw/{clip}.mp4: {n}x")
        print()
        print(f"Never-used clips ({len(report['never_used_clips'])}):")
        print(f"  {report['never_used_clips']}")
