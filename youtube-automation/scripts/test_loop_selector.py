#!/usr/bin/env python3
"""Focused tests for the intelligent loop-method selector (owner direction,
2026-08-01): scripts/motion_decision.py and scripts/loop_builder.py.

No pytest dependency in this project — run directly:
  python3 scripts/test_loop_selector.py

Uses small synthetic clips generated on the fly (fast, no repo assets
required) so this can run standalone in CI or locally.
"""
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(__file__))

from motion_decision import validate_decision, format_log_line
from loop_builder import build_reverse_loop, build_crossfade_loop, get_duration

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


def make_solid_clip(path, duration=3.0, size="320x180", fps=15, color="0x224488"):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s={size}:d={duration}:r={fps}",
         "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", path],
        capture_output=True, check=True,
    )


def extract_frame(clip, t, out_png, from_end=False):
    if from_end:
        cmd = ["ffmpeg", "-y", "-sseof", f"-{t}", "-i", clip, "-update", "1", "-vframes", "1", out_png]
    else:
        cmd = ["ffmpeg", "-y", "-ss", str(t), "-i", clip, "-vframes", "1", out_png]
    subprocess.run(cmd, capture_output=True, check=True)


def mean_abs_diff(png_a, png_b):
    from PIL import Image, ImageChops
    import numpy as np
    a = Image.open(png_a).convert("RGB")
    b = Image.open(png_b).convert("RGB")
    return float(np.array(ImageChops.difference(a, b)).mean())


def test_motion_decision_schema():
    print("motion_decision.validate_decision()")
    valid = {
        "loop_method": "crossfade",
        "confidence": 0.9,
        "significant_subject_motion": False,
        "camera_motion": False,
        "motion_summary": "Falling snow only, camera static.",
        "reason": "Only ambient motion present.",
    }
    check("accepts a well-formed decision", validate_decision(dict(valid)) == valid)
    check("format_log_line renders all 4 required lines",
          format_log_line(valid).count("\n") == 3)

    for field, bad_value, label in [
        ("loop_method", "zigzag", "bad loop_method"),
        ("confidence", 1.5, "out-of-range confidence"),
        ("confidence", -0.1, "negative confidence"),
        ("significant_subject_motion", "yes", "non-bool significant_subject_motion"),
        ("camera_motion", 1, "non-bool camera_motion"),
        ("motion_summary", "   ", "empty motion_summary"),
        ("reason", "", "empty reason"),
    ]:
        bad = dict(valid)
        bad[field] = bad_value
        try:
            validate_decision(bad)
            check(f"rejects {label}", False, "(did not raise)")
        except ValueError:
            check(f"rejects {label}", True)

    missing = dict(valid)
    del missing["camera_motion"]
    try:
        validate_decision(missing)
        check("rejects missing required key", False, "(did not raise)")
    except ValueError:
        check("rejects missing required key", True)


def test_reverse_loop(tmpdir):
    print("loop_builder.build_reverse_loop() — moving-subject case (mechanics)")
    src = os.path.join(tmpdir, "src_reverse.mp4")
    out = os.path.join(tmpdir, "out_reverse.mp4")
    make_solid_clip(src, duration=2.0, fps=12)

    build_reverse_loop(src, out)
    check("output file created", os.path.exists(out))

    src_dur = get_duration(src)
    out_dur = get_duration(out)
    check("reverse loop is longer than the source (ramp expands duration)", out_dur > src_dur,
          f"src={src_dur:.3f} out={out_dur:.3f}")

    first_png = os.path.join(tmpdir, "rev_first.png")
    last_png = os.path.join(tmpdir, "rev_last.png")
    extract_frame(out, 0, first_png)
    extract_frame(out, 0.15, last_png, from_end=True)
    diff = mean_abs_diff(first_png, last_png)
    check("ping-pong loop junction is a near-exact frame match", diff < 2.0, f"mean_abs_diff={diff:.3f}")


def test_crossfade_loop(tmpdir):
    print("loop_builder.build_crossfade_loop() — ambient-only case (mechanics)")
    src = os.path.join(tmpdir, "src_crossfade.mp4")
    out = os.path.join(tmpdir, "out_crossfade.mp4")
    make_solid_clip(src, duration=5.0, fps=12)

    build_crossfade_loop(src, out)
    check("output file created", os.path.exists(out))

    src_dur = get_duration(src)
    out_dur = get_duration(out)
    expected_x = min(2.0, max(0.6, src_dur * 0.12))
    expected_out_dur = src_dur - expected_x
    check("crossfade loop duration matches D - X formula", abs(out_dur - expected_out_dur) < 0.2,
          f"expected~{expected_out_dur:.3f} got={out_dur:.3f}")

    # A solid-color source means the blended seam should be visually seamless
    # (blending a color with itself changes nothing) — a strong, deterministic
    # regression check that the junction isn't a black frame or a hard cut.
    first_png = os.path.join(tmpdir, "cf_first.png")
    last_png = os.path.join(tmpdir, "cf_last.png")
    extract_frame(out, 0, first_png)
    extract_frame(out, 0.15, last_png, from_end=True)
    diff = mean_abs_diff(first_png, last_png)
    check("crossfade loop junction is seamless on a static source", diff < 2.0, f"mean_abs_diff={diff:.3f}")


def test_crossfade_min_clean_middle_guard(tmpdir):
    print("loop_builder.build_crossfade_loop() — short-clip safety guard")
    src = os.path.join(tmpdir, "src_short.mp4")
    out = os.path.join(tmpdir, "out_short.mp4")
    # A very short clip (0.5s) would want a formula crossfade of 0.6s, longer
    # than the clip itself — the guard must shrink it rather than crash or
    # produce a degenerate/negative-length loop.
    make_solid_clip(src, duration=0.5, fps=12)
    try:
        build_crossfade_loop(src, out)
        check("short clip doesn't crash (guard shrinks crossfade duration)", os.path.exists(out))
    except ValueError:
        # Also acceptable: explicitly refuses rather than producing garbage.
        check("short clip explicitly refused rather than producing a bad loop", True)


def main():
    with tempfile.TemporaryDirectory() as tmpdir:
        test_motion_decision_schema()
        test_reverse_loop(tmpdir)
        test_crossfade_loop(tmpdir)
        test_crossfade_min_clean_middle_guard(tmpdir)

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
