#!/usr/bin/env bash
# Agent 5 (Assembler): loop a silent visual segment and an audio track
# independently to a target duration, then mux them together with fade
# in/out, without re-encoding every repeat (uses -stream_loop + concat
# where practical to keep this cheap).
#
# Usage:
#   ffmpeg_loop.sh <visual_loop_segment> <audio_track> <target_minutes> <output_file>

set -euo pipefail

VIDEO_LOOP="$1"
AUDIO_TRACK="$2"
TARGET_MINUTES="$3"
OUTPUT="$4"

TARGET_SECONDS=$((TARGET_MINUTES * 60))
FADE_DUR=7

# -stream_loop -1 loops the input indefinitely; -t caps total output duration.
# This avoids concatenating N physical copies, keeping disk/CPU cost flat
# regardless of target length.
ffmpeg -y \
  -stream_loop -1 -i "$VIDEO_LOOP" \
  -stream_loop -1 -i "$AUDIO_TRACK" \
  -t "$TARGET_SECONDS" \
  -filter_complex "\
    [0:v]fade=t=in:st=0:d=${FADE_DUR},fade=t=out:st=$((TARGET_SECONDS - FADE_DUR)):d=${FADE_DUR}[v]; \
    [1:a]afade=t=in:st=0:d=${FADE_DUR},afade=t=out:st=$((TARGET_SECONDS - FADE_DUR)):d=${FADE_DUR}[a]" \
  -map "[v]" -map "[a]" \
  -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 160k \
  -shortest \
  "$OUTPUT"

ACTUAL_DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT")
echo "Assembled loop: target=${TARGET_SECONDS}s actual=${ACTUAL_DURATION}s -> $OUTPUT"
