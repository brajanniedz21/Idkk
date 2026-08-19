#!/usr/bin/env python3
"""Focused tests for scripts/clip_pool_status.py (owner-reported real bug,
2026-08-02: raw/68.mp4 and raw/65.mp4 reused across 3 published Shorts in a
row because clip reuse had no real enforcement).

No pytest dependency in this project — run directly:
  python3 scripts/test_clip_pool_status.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import clip_pool_status as cps

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


def make_queue(candidates):
    return {"queue": candidates}


def test_structured_field_preferred():
    print("1. clips_used_for_candidate() prefers the structured field over transform_log prose")
    c = {"clips_used": ["9", "19"], "transform_log": "uses (raw/1,2,3.mp4)"}
    check("structured field wins", cps.clips_used_for_candidate(c) == ["9", "19"])


def test_fallback_to_transform_log():
    print("2. Falls back to parsing transform_log prose when clips_used is absent")
    c = {"transform_log": "7 shots from 8 distinct clips supplied (raw/9,19,29,45.mp4; extra note)"}
    check("parsed from prose", cps.clips_used_for_candidate(c) == ["9", "19", "29", "45"])


def test_no_data_returns_empty():
    print("3. No clips_used and no parseable transform_log returns []")
    c = {"transform_log": "no clip mentions here at all"}
    check("empty list, not a crash", cps.clips_used_for_candidate(c) == [])


def test_cooldown_set_last_n():
    print("4. recently_used_clips() only looks at the most recent N published candidates")
    candidates = [
        {"id": "sf_001", "status": "published", "published_at": "2026-07-27T00:00:00Z", "clips_used": ["1", "2"]},
        {"id": "sf_002", "status": "published", "published_at": "2026-07-28T00:00:00Z", "clips_used": ["3", "4"]},
        {"id": "sf_003", "status": "published", "published_at": "2026-07-29T00:00:00Z", "clips_used": ["5", "6"]},
        {"id": "sf_004", "status": "published", "published_at": "2026-07-30T00:00:00Z", "clips_used": ["7", "8"]},
        {"id": "sf_005", "status": "published", "published_at": "2026-07-31T00:00:00Z", "clips_used": ["9", "10"]},
        {"id": "sf_006", "status": "published", "published_at": "2026-08-01T00:00:00Z", "clips_used": ["11", "12"]},
    ]
    queue = make_queue(candidates)
    cooldown, recent = cps.recently_used_clips(queue, lookback=5)
    check("cooldown excludes the oldest candidate's clips", "1" not in cooldown and "2" not in cooldown)
    check("cooldown includes the 5 most recent candidates' clips", cooldown == {"3", "4", "5", "6", "7", "8", "9", "10", "11", "12"})
    check("5 most recent candidates identified, newest first", [c["id"] for c in recent] == ["sf_006", "sf_005", "sf_004", "sf_003", "sf_002"])


def test_unpublished_candidates_excluded():
    print("5. Unpublished/quarantined candidates never count toward the cooldown set")
    candidates = [
        {"id": "sf_001", "status": "published", "published_at": "2026-07-27T00:00:00Z", "clips_used": ["1"]},
        {"id": "sf_002", "status": "quarantined", "published_at": None, "clips_used": ["99"]},
        {"id": "sf_003", "status": "produced", "clips_used": ["98"]},
    ]
    queue = make_queue(candidates)
    cooldown, recent = cps.recently_used_clips(queue, lookback=5)
    check("only the published candidate counts", cooldown == {"1"})
    check("quarantined/produced clips never enter the cooldown set", "99" not in cooldown and "98" not in cooldown)


def test_missing_timestamp_falls_back_to_posted_history():
    print("5b. A published candidate with no timestamp on its own entry still sorts correctly via posted_history.json fallback (real bug, 2026-08-03: sf_034 was silently excluded from the cooldown window because its queue entry had no published_at, produced_at, or scripted_at set after publish)")
    candidates = [
        {"id": "sf_001", "status": "published", "published_at": "2026-07-27T00:00:00Z", "clips_used": ["1"]},
        {"id": "sf_002", "status": "published", "published_at": "2026-07-28T00:00:00Z", "clips_used": ["2"]},
        {"id": "sf_003", "status": "published", "clips_used": ["3"]},  # no timestamp anywhere on the entry itself
    ]
    queue = make_queue(candidates)
    posted_history = {"short_form": [
        {"candidate_id": "sf_003", "published_at": "2026-07-29T00:00:00Z"},
    ]}
    # Without the fallback, sf_003 would sort as the OLDEST (empty string sort key) and drop out of a lookback=2 window.
    cooldown_without_fallback, recent_without_fallback = cps.recently_used_clips(queue, lookback=2)
    check("without fallback, sf_003 is silently excluded (the bug)", "3" not in cooldown_without_fallback)

    cooldown_with_fallback, recent_with_fallback = cps.recently_used_clips(queue, lookback=2, posted_history=posted_history)
    check("with fallback, sf_003 is correctly the most recent", recent_with_fallback[0]["id"] == "sf_003")
    check("with fallback, sf_003's clip is in the cooldown set", "3" in cooldown_with_fallback)
    check("with fallback, sf_002 still makes the lookback=2 window", recent_with_fallback[1]["id"] == "sf_002")


def test_reproduces_the_real_bug_report():
    print("6. Reproduces the real owner-reported bug: raw/68 and raw/65 reused across sf_022/023/024")
    candidates = [
        {"id": "sf_022", "status": "published", "published_at": "2026-07-31T08:00:00Z", "clips_used": ["68", "65", "17", "18", "69", "41", "21"]},
        {"id": "sf_023", "status": "published", "published_at": "2026-07-31T13:00:00Z", "clips_used": ["66", "67", "13", "65", "68", "70"]},
        {"id": "sf_024", "status": "published", "published_at": "2026-07-31T18:00:00Z", "clips_used": ["69", "66", "68", "65", "21", "36"]},
    ]
    queue = make_queue(candidates)
    report = cps.usage_report(queue, lookback=5)
    check("raw/68 flagged as a real violation within the cooldown window", report["recent_window_violations"].get("68") == 3)
    check("raw/65 flagged as a real violation within the cooldown window", report["recent_window_violations"].get("65") == 3)
    # And the fix works going forward: the cooldown set correctly blocks a 4th reuse.
    cooldown, _ = cps.recently_used_clips(queue, lookback=5)
    check("cooldown set correctly blocks raw/68 for the next candidate", "68" in cooldown)
    check("cooldown set correctly blocks raw/65 for the next candidate", "65" in cooldown)


def test_pool_size_from_real_directory():
    print("7. pool_size() counts actual files, not a hard-coded/documentation number")
    size = cps.pool_size()
    check("pool size is a real positive count", isinstance(size, int) and size > 0, detail=f"(got {size})")


def main():
    test_structured_field_preferred()
    test_fallback_to_transform_log()
    test_no_data_returns_empty()
    test_cooldown_set_last_n()
    test_unpublished_candidates_excluded()
    test_missing_timestamp_falls_back_to_posted_history()
    test_reproduces_the_real_bug_report()
    test_pool_size_from_real_directory()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
