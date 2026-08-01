#!/usr/bin/env python3
"""Focused tests for scripts/analytics_intelligence.py (owner direction,
2026-08-01, Analytics Intelligence and Self-Improvement Protocol).

No pytest dependency in this project — run directly:
  python3 scripts/test_analytics_intelligence.py

Uses small synthetic data and a scratch copy of performance_notes.json's
shape (never writes to the real state/ files) so this is safe to run
repeatedly without touching production state.
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(__file__))
import analytics_intelligence as ai

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} {detail}")


def test_safe_math():
    print("safe_div / rate_per_1000 / age_days")
    check("safe_div handles zero denominator", ai.safe_div(5, 0) is None)
    check("safe_div handles None denominator", ai.safe_div(5, None) is None)
    check("safe_div normal case", ai.safe_div(10, 4) == 2.5)

    check("rate_per_1000 zero views -> None", ai.rate_per_1000(5, 0) is None)
    check("rate_per_1000 None views -> None", ai.rate_per_1000(5, None) is None)
    check("rate_per_1000 normal case", ai.rate_per_1000(10, 1000) == 10.0)

    check("age_days missing published_at -> None", ai.age_days(None) is None)
    check("age_days unparseable -> None", ai.age_days("not-a-date") is None)
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    check("age_days 2 days ago ~= 2.0",
          abs(ai.age_days("2026-07-30T00:00:00Z", now=now) - 2.0) < 0.01)
    check("age_days floors near-zero age instead of dividing by ~0",
          ai.age_days("2026-08-01T00:00:00Z", now=now) == 0.05)


def test_age_normalized_views():
    print("age_normalized_views")
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    v = ai.age_normalized_views(200, "2026-07-30T00:00:00Z", now=now)
    check("200 views over 2 days -> 100/day", abs(v - 100.0) < 0.01)
    check("missing views -> None", ai.age_normalized_views(None, "2026-07-30T00:00:00Z", now=now) is None)
    check("missing published_at -> None", ai.age_normalized_views(200, None, now=now) is None)


def test_median_and_baseline():
    print("median / format_baseline")
    check("median of empty list is None", ai.median([]) is None)
    check("median ignores None entries", ai.median([None, 1, 2, 3]) == 2)
    check("median is robust to one outlier vs mean",
          ai.median([10, 12, 11, 1000]) == 11.5)  # mean would be ~258

    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    videos = [
        {"views": 100, "likes": 5, "comments": 1, "published_at": "2026-07-31T00:00:00Z"},
        {"views": 200, "likes": 10, "comments": 2, "published_at": "2026-07-30T00:00:00Z"},
        {"views": 50, "likes": 0, "comments": 0, "published_at": "2026-07-29T00:00:00Z"},
    ]
    baseline = ai.format_baseline(videos, now=now)
    check("baseline reports correct n", baseline["n"] == 3)
    check("baseline median_views is the middle value", baseline["median_views"] == 100)
    check("baseline includes age-normalized median", baseline["median_age_normalized_views"] is not None)
    check("baseline includes like-rate median", baseline["median_likes_per_1000_views"] is not None)

    empty_baseline = ai.format_baseline([], now=now)
    check("empty group baseline doesn't crash, reports n=0", empty_baseline["n"] == 0)
    check("empty group baseline medians are None", empty_baseline["median_views"] is None)


def test_evidence_levels():
    print("classify_evidence_level")
    check("0 samples -> None", ai.classify_evidence_level(0) is None)
    check("1 sample -> observation", ai.classify_evidence_level(1) == "observation")
    check("2 samples -> early_signal", ai.classify_evidence_level(2) == "early_signal")
    check("3 samples -> repeated_pattern", ai.classify_evidence_level(3) == "repeated_pattern")
    check("10 samples -> still repeated_pattern (never auto strong_channel_pattern)",
          ai.classify_evidence_level(10) == "repeated_pattern")


def test_join_video_attributes():
    print("join_video_attributes")
    video_analytics = {
        "videos": [
            {"video_id": "vid1", "format": "short", "views": 100, "likes": 5, "comments": 1, "published_at": "2026-07-31T00:00:00Z"},
            {"video_id": "vid_unmatched", "format": "short", "views": 50, "likes": 1, "comments": 0, "published_at": "2026-07-30T00:00:00Z"},
        ]
    }
    short_queue = {
        "queue": [
            {"id": "sf_001", "published_video_id": "vid1", "angle": "test angle", "title_pattern": "Test Title", "trending_sound_style": "upbeat"},
        ]
    }
    long_queue = {"queue": []}

    joined = ai.join_video_attributes(video_analytics, short_queue, long_queue)
    check("joins correct count", len(joined) == 2)
    matched = next(v for v in joined if v["video_id"] == "vid1")
    check("matched video gets angle", matched["angle"] == "test angle")
    check("matched video has no missing_attributes", matched["missing_attributes"] == [])
    unmatched = next(v for v in joined if v["video_id"] == "vid_unmatched")
    check("unmatched video's angle is None", unmatched["angle"] is None)
    check("unmatched video reports missing_attributes, doesn't fabricate them",
          set(unmatched["missing_attributes"]) == {"candidate_id", "angle", "title_pattern", "sound_style"})


def test_run_id_and_append():
    print("make_run_id / append_performance_notes_cycle (scratch file only)")
    now = datetime(2026, 8, 2, 14, 5, tzinfo=timezone.utc)
    run_id = ai.make_run_id(now=now)
    check("run_id has expected shape", run_id == "analytics-2026-08-02-1405")

    with tempfile.TemporaryDirectory() as tmpdir:
        scratch = os.path.join(tmpdir, "performance_notes.json")
        original = {
            "_comment": "scratch copy for testing",
            "cycles": [{"run_id": "analytics-2026-08-01-1900", "run_date": "2026-08-01T19:00:00Z"}],
            "competitor_scan_example": {"note": "must survive untouched"},
        }
        with open(scratch, "w") as f:
            json.dump(original, f)

        n = ai.append_performance_notes_cycle({"run_id": run_id, "run_date": now.isoformat()}, path=scratch)
        check("append returns new cycle count", n == 2)

        with open(scratch) as f:
            reread = json.load(f)
        check("prior cycle entry preserved", reread["cycles"][0]["run_id"] == "analytics-2026-08-01-1900")
        check("new cycle entry appended at end", reread["cycles"][1]["run_id"] == run_id)
        check("other top-level keys untouched", reread["competitor_scan_example"] == {"note": "must survive untouched"})

        try:
            ai.append_performance_notes_cycle({"run_id": run_id, "run_date": now.isoformat()}, path=scratch)
            check("duplicate run_id is rejected", False, "(did not raise)")
        except ValueError:
            check("duplicate run_id is rejected", True)


def test_real_state_files_readable():
    print("sanity check against the real project state files (read-only)")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state = os.path.join(root, "state")
    try:
        va = json.load(open(os.path.join(state, "video_analytics.json")))
        sq = json.load(open(os.path.join(state, "short_form_queue.json")))
        lq = json.load(open(os.path.join(state, "long_form_queue.json")))
    except FileNotFoundError as e:
        check("real state files present", False, str(e))
        return

    joined = ai.join_video_attributes(va, sq, lq)
    check("join runs without error against real project state", isinstance(joined, list))
    shorts = [v for v in joined if v.get("format") == "short"]
    longs = [v for v in joined if v.get("format") == "long"]
    short_baseline = ai.format_baseline(shorts)
    long_baseline = ai.format_baseline(longs)
    check("short baseline n matches joined short count", short_baseline["n"] == len(shorts))
    check("long baseline n matches joined long count", long_baseline["n"] == len(longs))


def main():
    test_safe_math()
    test_age_normalized_views()
    test_median_and_baseline()
    test_evidence_levels()
    test_join_video_attributes()
    test_run_id_and_append()
    test_real_state_files_readable()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
