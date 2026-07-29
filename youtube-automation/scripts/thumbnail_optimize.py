#!/usr/bin/env python3
"""
Thumbnail optimization pass (the "Curiosity Engine" thumbnail stage, owner
direction 2026-07-30). Takes a source frame/image (a sourced long-form
background, or a frame extracted from a produced short) and applies a
click-through-oriented enhancement pass while preserving realism:

  - slight brightness lift
  - slight contrast boost
  - local sharpness (unsharp mask) so the subject reads crisply at small sizes
  - slight color/saturation lift, capped well short of oversaturation
  - shadow lift (gamma curve favoring shadows over highlights) so detail in
    dark luxury-night scenes doesn't just crush to black at thumbnail size
  - resize/crop to YouTube's 1280x720 thumbnail spec

"Billboard principle" check: also writes a 120px-wide preview alongside the
full-size output. The pipeline's own agent (not a human) is expected to
actually look at that 120px preview as part of the content_quality_gate
"thumbnail_strength" score in config/gates.json — this script only produces
the preview, it doesn't itself judge legibility.

Usage:
    python3 thumbnail_optimize.py --input path/to/frame.jpg --output path/to/thumb.jpg \
        [--billboard-preview path/to/preview_120.jpg]
"""
import argparse

from PIL import Image, ImageEnhance, ImageFilter

THUMB_SIZE = (1280, 720)

# Tuned deliberately conservative — "slightly" per the brief, not a dramatic
# grade change. Each factor is a multiplier on the original (1.0 = no change).
BRIGHTNESS_FACTOR = 1.06
CONTRAST_FACTOR = 1.12
COLOR_FACTOR = 1.10          # saturation/color depth — capped short of oversaturation
SHARPNESS_UNSHARP = dict(radius=2.2, percent=110, threshold=3)
SHADOW_LIFT_GAMMA = 0.90     # <1.0 brightens shadows more than highlights


def _shadow_lift(im, gamma=SHADOW_LIFT_GAMMA):
    """Gamma curve applied per-channel: brightens shadow detail without
    flattening or blowing out highlights, since gamma<1 curves upward faster
    near black than near white."""
    table = [min(255, int((v / 255.0) ** gamma * 255.0 + 0.5)) for v in range(256)]
    lut = table * 3  # same curve for R, G, B
    return im.point(lut)


def optimize_thumbnail(src_path, out_path, billboard_preview_path=None, target_size=THUMB_SIZE):
    im = Image.open(src_path).convert("RGB")

    # Fill-crop to the 16:9 thumbnail aspect ratio without squashing.
    tw, th = target_size
    sw, sh = im.size
    target_ratio, src_ratio = tw / th, sw / sh
    if src_ratio > target_ratio:
        new_w = int(sh * target_ratio)
        left = (sw - new_w) // 2
        im = im.crop((left, 0, left + new_w, sh))
    elif src_ratio < target_ratio:
        new_h = int(sw / target_ratio)
        top = (sh - new_h) // 2
        im = im.crop((0, top, sw, top + new_h))
    im = im.resize(target_size, Image.LANCZOS)

    im = _shadow_lift(im)
    im = ImageEnhance.Brightness(im).enhance(BRIGHTNESS_FACTOR)
    im = ImageEnhance.Contrast(im).enhance(CONTRAST_FACTOR)
    im = ImageEnhance.Color(im).enhance(COLOR_FACTOR)
    im = im.filter(ImageFilter.UnsharpMask(**SHARPNESS_UNSHARP))

    im.save(out_path, "JPEG", quality=92)

    if billboard_preview_path:
        preview_h = max(1, round(120 * target_size[1] / target_size[0]))
        preview = im.resize((120, preview_h), Image.LANCZOS)
        preview.save(billboard_preview_path, "JPEG", quality=90)

    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--billboard-preview", default=None,
                     help="Optional path to save a 120px-wide preview for the billboard-principle check.")
    args = ap.parse_args()

    optimize_thumbnail(args.input, args.output, args.billboard_preview)
    print(f"wrote {args.output}" + (f" + billboard preview {args.billboard_preview}" if args.billboard_preview else ""))


if __name__ == "__main__":
    main()
