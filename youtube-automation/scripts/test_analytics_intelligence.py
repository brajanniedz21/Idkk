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


def test_cadence_timezone():
    print("local_time_info / time_block (Europe/London, DST-aware)")
    winter = ai.local_time_info("2026-01-15T20:00:00Z")  # GMT, UTC+0
    summer = ai.local_time_info("2026-07-15T20:00:00Z")  # BST, UTC+1
    check("winter (GMT) hour matches UTC exactly", winter["hour"] == 20)
    check("summer (BST) hour is UTC+1, not a fixed offset", summer["hour"] == 21)
    check("winter 20:00 time_block is evening", winter["time_block"] == "evening")
    check("summer time_block is evening", summer["time_block"] == "evening")
    check("missing published_at returns None, not a fabricated guess", ai.local_time_info(None) is None)
    check("time_block boundaries: 6->morning, 11->morning, 12->afternoon",
          ai.time_block(6) == "morning" and ai.time_block(11) == "morning" and ai.time_block(12) == "afternoon")
    check("time_block boundaries: 16->afternoon, 17->evening, 21->evening, 22->late_night",
          ai.time_block(16) == "afternoon" and ai.time_block(17) == "evening"
          and ai.time_block(21) == "evening" and ai.time_block(22) == "late_night")


def test_cadence_spacing():
    print("hours_between / cadence_features")
    check("hours_between computes correctly", ai.hours_between("2026-01-01T00:00:00Z", "2026-01-02T06:00:00Z") == 30.0)
    check("hours_between missing input -> None", ai.hours_between(None, "2026-01-01T00:00:00Z") is None)

    v = {"video_id": "v3", "format": "short", "published_at": "2026-01-02T12:00:00Z"}
    prev_same = {"video_id": "v2", "published_at": "2026-01-02T09:00:00Z"}
    prev_any = {"video_id": "v_long", "published_at": "2026-01-01T20:00:00Z"}
    feats = ai.cadence_features(v, previous_same_format=prev_same, previous_any_format=prev_any)
    check("hours_since_previous_same_format correct", feats["hours_since_previous_same_format"] == 3.0)
    check("hours_since_previous_any_format correct", feats["hours_since_previous_any_format"] == 16.0)
    check("local_time populated", feats["local_time"] is not None)

    first_of_kind = ai.cadence_features(v, previous_same_format=None, previous_any_format=None)
    check("first upload of its kind has no spacing (not fabricated as 0)",
          first_of_kind["hours_since_previous_same_format"] is None)


def test_group_baseline_by_key():
    print("group_baseline_by_key")
    now = datetime(2026, 8, 1, tzinfo=timezone.utc)
    videos = [
        {"video_id": "e1", "views": 100, "likes": 5, "comments": 1, "published_at": "2026-07-31T19:00:00Z"},  # evening
        {"video_id": "e2", "views": 200, "likes": 8, "comments": 2, "published_at": "2026-07-30T18:30:00Z"},  # evening
        {"video_id": "m1", "views": 50, "likes": 1, "comments": 0, "published_at": "2026-07-30T07:00:00Z"},   # morning
    ]
    grouped = ai.group_baseline_by_key(videos, lambda v: ai.local_time_info(v["published_at"])["time_block"], now=now)
    check("groups by time block correctly", set(grouped) == {"evening", "morning"})
    check("evening group has n=2", grouped["evening"]["n"] == 2)
    check("morning group has n=1", grouped["morning"]["n"] == 1)


def test_fatigue_assessment():
    print("fatigue_assessment — the spec's own worked scenarios")
    now = datetime(2026, 8, 10, tzinfo=timezone.utc)

    def mk(vid, days_ago, views):
        ts = (now - __import__("datetime").timedelta(days=days_ago)).isoformat()
        return {"video_id": vid, "format": "short", "views": views, "likes": 5, "comments": 1, "published_at": ts}

    # Frequent but consistently strong -> diversify, never reduce/retire on frequency alone.
    pattern_strong = [mk("p4", 1, 600), mk("p3", 3, 650), mk("p2", 5, 700), mk("p1", 7, 680)]
    same_format = [mk("p4", 1, 600), mk("o1", 2, 200), mk("p3", 3, 650), mk("o2", 4, 180),
                    mk("p2", 5, 700), mk("o3", 6, 150), mk("p1", 7, 680)]
    baseline = ai.format_baseline(same_format, now=now)
    result = ai.fatigue_assessment(pattern_strong, same_format, baseline, now=now)
    check("frequent + strong performance -> diversify, not reduce/retire", result["fatigue_status"] == "diversify")

    # Frequent AND declining -> fatigue_detected.
    pattern_declining = [mk("q4", 1, 50), mk("q3", 2, 60), mk("q2", 3, 55), mk("q1", 8, 800)]
    same_format2 = [mk("q4", 1, 50), mk("q3", 2, 60), mk("q2", 3, 55), mk("x1", 5, 200), mk("q1", 8, 800)]
    baseline2 = ai.format_baseline(same_format2, now=now)
    result2 = ai.fatigue_assessment(pattern_declining, same_format2, baseline2, now=now)
    check("frequent + declining -> fatigue_detected", result2["fatigue_status"] == "fatigue_detected")

    # One weak use never proves fatigue.
    result3 = ai.fatigue_assessment([mk("r1", 1, 10)], same_format, baseline, now=now)
    check("single use -> healthy (one weak repetition doesn't prove fatigue)", result3["fatigue_status"] == "healthy")

    # Never mixes formats: a long-form pattern must never be judged against a short baseline.
    check("consecutive_uses counts correctly for the strong pattern",
          result["recent_usage"]["consecutive_uses"] == 1)  # p4 then a non-pattern video breaks the streak
    check("share_of_last_10 is a real fraction, not fabricated", 0 < result["recent_usage"]["share_of_last_10"] < 1)


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


def test_is_live_video():
    print("is_live_video / filter_live_videos")
    now = datetime(2026, 8, 5, 7, 0, tzinfo=timezone.utc)
    live = {"published_at": "2026-08-04T16:25:53Z", "views": 61}
    scheduled = {"published_at": "2026-08-08T11:00:00Z", "views": 1}
    missing = {"views": 5}
    bad_format = {"published_at": "not-a-date", "views": 5}
    check("a past published_at is live", ai.is_live_video(live, now=now) is True)
    check("a future published_at is not live", ai.is_live_video(scheduled, now=now) is False)
    check("no published_at is not live", ai.is_live_video(missing, now=now) is False)
    check("unparseable published_at is not live", ai.is_live_video(bad_format, now=now) is False)

    videos = [live, scheduled, missing, bad_format]
    filtered = ai.filter_live_videos(videos, now=now)
    check("filter_live_videos keeps only the genuinely live entry", filtered == [live])

    # Real regression this guards against: a future-published (still-private,
    # scheduled) video must not silently inflate/dilute a performance baseline.
    baseline_all = ai.format_baseline(videos, now=now)
    baseline_live = ai.format_baseline(filtered, now=now)
    check(
        "baseline over live-only videos differs from baseline over all videos when a future-scheduled one is mixed in",
        baseline_all["n"] != baseline_live["n"],
    )


def main():
    test_safe_math()
    test_age_normalized_views()
    test_median_and_baseline()
    test_evidence_levels()
    test_join_video_attributes()
    test_run_id_and_append()
    test_cadence_timezone()
    test_cadence_spacing()
    test_group_baseline_by_key()
    test_fatigue_assessment()
    test_is_live_video()
    test_real_state_files_readable()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
