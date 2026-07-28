#!/usr/bin/env python3
"""
Generate a tileable rain-streak overlay (RGBA PNG) and composite it onto a
still image as a scrolling, seamlessly-loopable rain animation.

Used by Agent 3.2 (long-form animator) so "rain-streaked window" candidates
get real animated rain instead of a static image + zoom. No external assets
or network calls — the streak texture is drawn procedurally with PIL, and
the "falling" motion is a vertical scroll of that texture wrapped with a
modulo offset in the ffmpeg overlay filter, which loops with zero seam as
long as scroll_speed * loop_seconds is a whole number of texture heights
(this script picks scroll_speed to guarantee that for the given duration).

Usage:
    python3 rain_overlay.py --image path/to/still.jpg --out path/to/loop.mp4 \\
        --seconds 20 --width 1920 --height 1080 [--intensity medium] [--zoom]
"""
import argparse
import math
import os
import random
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter


def make_rain_texture(width, height, intensity="medium", seed=7):
    """A vertically-tileable RGBA streak texture. Tileable means: content
    drawn near the bottom edge wraps and reappears near the top, so scrolling
    this texture in a loop never shows a seam."""
    rng = random.Random(seed)
    density = {"light": 90, "medium": 160, "heavy": 260}.get(intensity, 160)

    tex = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tex)

    for _ in range(density):
        x = rng.uniform(0, width)
        y = rng.uniform(0, height)
        length = rng.uniform(14, 46)
        # Slight diagonal (wind drift) rather than perfectly vertical —
        # reads as real rain, not a scrolling barcode pattern.
        dx = rng.uniform(-4, -1)
        alpha = rng.randint(28, 90)
        thickness = 1 if rng.random() < 0.75 else 2
        color = (200, 210, 225, alpha)

        # Draw the streak, wrapping across the bottom/top edge so the
        # texture tiles vertically with no visible cut.
        for wrap in (0, height, -height):
            y0 = y + wrap
            y1 = y0 + length
            if y1 < -50 or y0 > height + 50:
                continue
            draw.line([(x, y0), (x + dx * (length / 20), y1)], fill=color, width=thickness)

    tex = tex.filter(ImageFilter.GaussianBlur(0.4))
    return tex


def build_command(image_path, out_path, seconds, width, height, intensity, zoom, tex_path):
    fps = 25
    total_frames = int(seconds * fps)

    # Scroll speed chosen so scroll_speed * seconds is an exact multiple of
    # the texture height -> overlay's y-offset (mod texture_height) is
    # identical at t=0 and t=seconds, so the loop wraps with zero visible
    # jump in the rain layer.
    tex_height = height
    loops_of_texture = 6  # how many times the texture scrolls fully during the clip
    scroll_speed = (loops_of_texture * tex_height) / seconds  # px/sec

    zoom_expr = ""
    if zoom:
        # Same slow symmetric ken-burns breathing used elsewhere in this
        # pipeline (see agents/long_form/3.2_animator.md), kept subtle so it
        # doesn't compete with the rain for attention.
        zoom_expr = (
            f"zoompan=z='1+0.015*(1-cos(2*PI*on/{total_frames}))':"
            f"d=1:s={width}x{height}:fps={fps},"
        )

    filter_complex = (
        f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},{zoom_expr}format=yuva420p[bg];"
        f"[1:v]scale={width}:{tex_height}[rain];"
        f"[bg][rain]overlay=x=0:y=mod(t*{scroll_speed:.4f}\\,{tex_height})-{tex_height}:"
        f"shortest=1[v]"
    )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-i", image_path,
        "-stream_loop", "-1", "-i", tex_path,
        "-t", str(seconds),
        "-filter_complex", filter_complex,
        "-map", "[v]",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        out_path,
    ]
    return cmd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--width", type=int, default=1920)
    ap.add_argument("--height", type=int, default=1080)
    ap.add_argument("--intensity", choices=["light", "medium", "heavy"], default="medium")
    ap.add_argument("--zoom", action="store_true", help="also apply the standard slow ken-burns breathing")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory() as td:
        tex_path = os.path.join(td, "rain_texture.png")
        tex = make_rain_texture(args.width, args.height, args.intensity)
        tex.save(tex_path)

        cmd = build_command(args.image, args.out, args.seconds, args.width, args.height, args.intensity, args.zoom, tex_path)
        print(" ".join(cmd))
        subprocess.run(cmd, check=True)

    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
