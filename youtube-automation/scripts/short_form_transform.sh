#!/usr/bin/env bash
# Apply Agent 3.1's mandatory transform checklist to a raw short-form clip:
# reframe to vertical, speed/color change, burned-in text, and audio replacement.
#
# Usage:
#   short_form_transform.sh <input_clip> <output_clip> <cc0_audio_track> \
#     <overlay_text> [speed] [duration_seconds]
#
# speed defaults to 1.0 (no change) - pass e.g. 0.95 or 1.08 to satisfy the
# "at least one of speed/color change" gate requirement if you don't also
# apply a color LUT.

set -euo pipefail

INPUT="$1"
OUTPUT="$2"
AUDIO="$3"
TEXT="$4"
SPEED="${5:-1.05}"
DURATION="${6:-30}"

# Escape single quotes in overlay text for drawtext
ESCAPED_TEXT=$(printf '%s' "$TEXT" | sed "s/'/\\\\'/g" | sed "s/:/\\\\:/g")

ffmpeg -y -i "$INPUT" -i "$AUDIO" \
  -filter_complex "\
    [0:v]crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920,\
    setpts=PTS/${SPEED},\
    eq=contrast=1.08:saturation=1.15:brightness=0.02,\
    drawtext=text='${ESCAPED_TEXT}':fontcolor=white:fontsize=64:\
      box=1:boxcolor=black@0.35:boxborderw=20:\
      x=(w-text_w)/2:y=h*0.72:line_spacing=10[v]; \
    [1:a]atrim=0:${DURATION},asetpts=PTS-STARTPTS[a]" \
  -map "[v]" -map "[a]" \
  -t "$DURATION" \
  -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k \
  "$OUTPUT"

echo "Transformed: crop->vertical, speed=${SPEED}x, color-grade, text-overlay, audio-replaced -> $OUTPUT"
