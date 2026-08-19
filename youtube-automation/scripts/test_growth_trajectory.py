#!/usr/bin/env python3
"""Focused tests for scripts/analytics_intelligence.py's growth-trajectory
functions (owner direction, 2026-08-02: 100k-subscriber objective by
2027-04-21).

No pytest dependency in this project — run directly:
  python3 scripts/test_growth_trajectory.py
"""
import os
import sys
from datetime import datetime, timezone

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


def make_growth_config():
    return {
        "objective": {"target_subscribers": 100000, "target_date": "2027-04-21"},
        "checkpoints": [
            {"date": "2026-08-31", "subscribers": 250},
            {"date": "2026-09-30", "subscribers": 1000},
            {"date": "2027-04-21", "subscribers": 100000},
        ],
        "trajectory_status_thresholds": {"green_min_pct_of_required_pace": 90, "amber_min_pct_of_required_pace": 70},
    }


def test_no_subscriber_data_is_insufficient_not_fabricated():
    print("1. No subscriber data at all yields insufficient_data, never a fabricated status")
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    traj = ai.calculate_trajectory(23, [], make_growth_config(), now=now)
    check("data_confidence is no_data", traj["data_confidence"] == "no_data")
    check("trajectory_status is insufficient_data, not GREEN/AMBER/RED", traj["trajectory_status"] == "insufficient_data")
    check("no pace fabricated", traj["pace_7day_subscribers_per_day"] is None)


def test_real_math_on_a_thin_but_real_series():
    print("2. Real 5-day series produces correct arithmetic (matches a hand-verified real pull)")
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    series = [
        {"date": "2026-07-27", "subscribers_gained": 2, "subscribers_lost": 1, "net": 1},
        {"date": "2026-07-28", "subscribers_gained": 6, "subscribers_lost": 2, "net": 4},
        {"date": "2026-07-29", "subscribers_gained": 7, "subscribers_lost": 3, "net": 4},
        {"date": "2026-07-30", "subscribers_gained": 7, "subscribers_lost": 2, "net": 5},
        {"date": "2026-07-31", "subscribers_gained": 0, "subscribers_lost": 0, "net": 0},
    ]
    traj = ai.calculate_trajectory(23, series, make_growth_config(), now=now)
    check("pace_7day is the real mean of available days (14/5=2.8)", abs(traj["pace_7day_subscribers_per_day"] - 2.8) < 0.001)
    check("pace_7day_days_of_data reflects only real rows, not a fabricated 7", traj["pace_7day_days_of_data"] == 5)
    check("data_confidence is low (fewer than 7 real days)", traj["data_confidence"] == "low")
    check("remaining_subscribers is exact", traj["remaining_subscribers"] == 99977)
    check("next checkpoint is the nearest future one", traj["next_checkpoint"]["date"] == "2026-08-31")


def test_thin_pace_below_required_yields_red():
    print("3. A pace well below the required pace to the next checkpoint is classified RED, not silently ignored")
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    series = [{"date": "2026-07-31", "subscribers_gained": 1, "subscribers_lost": 0, "net": 1}] * 5
    traj = ai.calculate_trajectory(23, series, make_growth_config(), now=now)
    check("classified RED under a clearly insufficient pace", traj["trajectory_status"] == "RED")


def test_pace_meeting_checkpoint_requirement_yields_green():
    print("4. A pace comfortably meeting the checkpoint requirement is classified GREEN")
    now = datetime(2026, 8, 2, tzinfo=timezone.utc)
    # Checkpoint: 250 by 2026-08-31 from 23 now — needs (250-23)/~29 days ≈ 7.8/day.
    series = [{"date": "2026-07-31", "subscribers_gained": 12, "subscribers_lost": 0, "net": 12}] * 7
    traj = ai.calculate_trajectory(23, series, make_growth_config(), now=now)
    check("classified GREEN when pace exceeds the requirement", traj["trajectory_status"] == "GREEN")


def test_never_compares_shorts_to_long_form():
    print("5. next_checkpoint() picks by date, not by whether current subscribers already exceed an earlier checkpoint's count")
    now = datetime(2026, 10, 15, tzinfo=timezone.utc)  # after the 2026-08-31 and 2026-09-30 checkpoints' dates
    cfg = make_growth_config()
    nc = ai.next_checkpoint(50000, cfg["checkpoints"], now=now)
    check("skips past-dated checkpoints even if their subscriber target wasn't hit", nc["date"] == "2027-04-21")


def test_remaining_days_never_negative():
    print("6. remaining_days floors at 0 rather than going negative past the target date")
    now = datetime(2027, 5, 1, tzinfo=timezone.utc)  # after target_date
    traj = ai.calculate_trajectory(50000, [], make_growth_config(), now=now)
    check("remaining_days is 0, not negative", traj["remaining_days"] == 0)
    check("required_daily_pace is None rather than a division by zero", traj["required_daily_pace"] is None)


def main():
    test_no_subscriber_data_is_insufficient_not_fabricated()
    test_real_math_on_a_thin_but_real_series()
    test_thin_pace_below_required_yields_red()
    test_pace_meeting_checkpoint_requirement_yields_green()
    test_never_compares_shorts_to_long_form()
    test_remaining_days_never_negative()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
