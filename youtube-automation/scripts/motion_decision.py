#!/usr/bin/env python3
"""Schema validation for the loop-method motion decision (owner direction,
2026-08-01). The decision itself is a judgment call made by whoever inspects
the contact sheet (scripts/loop_contact_sheet.py's output) — this module just
makes sure that decision is structurally well-formed before it's trusted to
pick which ffmpeg pipeline runs in scripts/loop_builder.py.
"""
import json

REQUIRED_KEYS = {
    "loop_method",
    "confidence",
    "significant_subject_motion",
    "camera_motion",
    "motion_summary",
    "reason",
}


def validate_decision(decision):
    """Raise ValueError on a malformed decision; return it unchanged if valid."""
    missing = REQUIRED_KEYS - set(decision)
    if missing:
        raise ValueError(f"motion decision missing required keys: {sorted(missing)}")

    if decision["loop_method"] not in ("reverse", "crossfade"):
        raise ValueError(f"loop_method must be 'reverse' or 'crossfade', got {decision['loop_method']!r}")

    confidence = float(decision["confidence"])
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"confidence must be in [0.0, 1.0], got {confidence}")

    for key in ("significant_subject_motion", "camera_motion"):
        if not isinstance(decision[key], bool):
            raise ValueError(f"{key} must be a boolean, got {type(decision[key]).__name__}")

    if not decision["motion_summary"].strip():
        raise ValueError("motion_summary must not be empty")
    if not decision["reason"].strip():
        raise ValueError("reason must not be empty")

    return decision


def format_log_line(decision):
    """Render the decision as the log block the loop-selector spec requires."""
    return (
        f"Loop method: {decision['loop_method']}\n"
        f"Confidence: {decision['confidence']:.2f}\n"
        f"Motion: {decision['motion_summary']}\n"
        f"Reason: {decision['reason']}"
    )


def load_decision(path):
    with open(path) as f:
        decision = json.load(f)
    return validate_decision(decision)
