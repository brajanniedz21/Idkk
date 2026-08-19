#!/usr/bin/env python3
"""Build a contact sheet of evenly-spaced frames from a long-form source clip.

Part of the intelligent seamless-loop selector (owner direction, 2026-08-01).
This script is purely mechanical (frame extraction + tiling) — it does not
decide reverse vs. crossfade itself. That judgment requires actually looking
at the frames (and optionally the source-generation prompt/scene metadata),
which is Agent 3.2's job when it inspects the sheet this script produces via
the Read tool, the same pattern already used for the thumbnail billboard
preview check in scripts/thumbnail_optimize.py.

Usage:
  python3 loop_contact_sheet.py --input clip.mp4 --output contact_sheet.png [--frames 10]
"""
import argparse
import json
import math
import os
import subprocess
import sys

from PIL import Image


def get_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def extract_contact_sheet(clip_path, out_path, num_frames=10, thumb_width=320):
    if not (8 <= num_frames <= 12):
        raise ValueError("num_frames should be 8-12 per the loop-selector spec")

    duration = get_duration(clip_path)

    # Evenly spaced timestamps across the whole clip. Inset the last one
    # slightly so ffmpeg -ss never seeks exactly at/past EOF (a real failure
    # mode: seeking to the last microsecond can return an empty frame).
    timestamps = [duration * i / (num_frames - 1) for i in range(num_frames)]
    timestamps[0] = max(timestamps[0], 0.0)
    timestamps[-1] = min(timestamps[-1], max(0.0, duration - 0.05))

    tmp_dir = out_path + "_frames_tmp"
    os.makedirs(tmp_dir, exist_ok=True)
    frame_paths = []
    try:
        for i, t in enumerate(timestamps):
            frame_path = os.path.join(tmp_dir, f"f{i:02d}.png")
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{t:.3f}", "-i", clip_path, "-vframes", "1", frame_path],
                capture_output=True, check=True,
            )
            frame_paths.append(frame_path)

        images = [Image.open(f) for f in frame_paths]
        w, h = images[0].size
        scale = thumb_width / w
        thumb_h = int(h * scale)
        thumbs = [im.resize((thumb_width, thumb_h), Image.LANCZOS) for im in images]

        cols = min(4, len(thumbs))
        rows = math.ceil(len(thumbs) / cols)
        sheet = Image.new("RGB", (cols * thumb_width, rows * thumb_h), (0, 0, 0))
        for idx, th in enumerate(thumbs):
            x = (idx % cols) * thumb_width
            y = (idx // cols) * thumb_h
            sheet.paste(th, (x, y))
        sheet.save(out_path)
    finally:
        for f in frame_paths:
            if os.path.exists(f):
                os.remove(f)
        if os.path.isdir(tmp_dir):
            os.rmdir(tmp_dir)

    return {
        "duration_sec": round(duration, 3),
        "num_frames": len(timestamps),
        "timestamps_sec": [round(t, 3) for t in timestamps],
        "contact_sheet_path": out_path,
        "grid": f"{cols}x{rows}",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--frames", type=int, default=10)
    args = parser.parse_args()

    try:
        result = extract_contact_sheet(args.input, args.output, num_frames=args.frames)
        print(json.dumps(result, indent=2))
    except Exception as e:
        print(f"CONTACT SHEET FAILED: {e}", file=sys.stderr)
        sys.exit(1)
