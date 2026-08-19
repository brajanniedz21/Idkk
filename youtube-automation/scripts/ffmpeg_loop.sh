#!/usr/bin/env bash
# Agent 5 (Assembler): loop a silent visual segment and an audio track
# independently to a target duration, then mux them together with fade
# in/out, without re-encoding every repeat (uses -stream_loop + concat
# where practical to keep this cheap).
#
# Also applies the Subscribe animation branding overlay (owner direction,
# 2026-08-01) when enabled in config/branding.json — this script is only
# ever used for long-form assembly, so no format switch is needed here;
# the config's own "enabled" flag is the single on/off control.
#
# Usage:
#   ffmpeg_loop.sh <visual_loop_segment> <audio_track> <target_minutes> <output_file>

set -euo pipefail

VIDEO_LOOP="$1"
AUDIO_TRACK="$2"
TARGET_MINUTES="$3"
OUTPUT="$4"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BRANDING_CONFIG="$REPO_ROOT/config/branding.json"

TARGET_SECONDS=$((TARGET_MINUTES * 60))
FADE_DUR=7

# Read the subscribe_animation block out of config/branding.json into shell
# vars, so every tunable value lives in one config file rather than being
# hard-coded here. Prints nothing (and BRANDING_ENABLED stays "false") if
# the config or block is missing, so this script degrades gracefully.
BRANDING_ENABLED="false"
if [ -f "$BRANDING_CONFIG" ]; then
  eval "$(python3 - "$BRANDING_CONFIG" <<'PYEOF'
import json, sys
path = sys.argv[1]
with open(path) as f:
    cfg = json.load(f)
sub = cfg.get("subscribe_animation", {})
if sub.get("enabled") and "long_form" in sub.get("applies_to_formats", []):
    print(f'BRANDING_ENABLED="true"')
    print(f'ASSET_PATH={json.dumps(sub["asset_path"])}')
    print(f'CHROMA_COLOR={json.dumps(sub["chromakey_color"])}')
    print(f'CHROMA_SIM={json.dumps(str(sub["chromakey_similarity"]))}')
    print(f'CHROMA_BLEND={json.dumps(str(sub["chromakey_blend"]))}')
    print(f'DESPILL_MIX={json.dumps(str(sub["despill_mix"]))}')
    print(f'ALPHA_FADE_START={json.dumps(str(sub["overlay_alpha_fade_start_sec"]))}')
    print(f'ALPHA_FADE_DUR={json.dumps(str(sub["overlay_alpha_fade_duration_sec"]))}')
    print(f'AUDIO_MIX_VOLUME={json.dumps(str(sub["audio_mix_volume"]))}')
else:
    print('BRANDING_ENABLED="false"')
PYEOF
)"
fi

if [ "$BRANDING_ENABLED" = "true" ]; then
  ASSET_ABS="$REPO_ROOT/$ASSET_PATH"
  if [ ! -f "$ASSET_ABS" ]; then
    echo "WARNING: branding.json has subscribe_animation enabled but asset not found at $ASSET_ABS — skipping overlay for this render" >&2
    BRANDING_ENABLED="false"
  fi
fi

if [ "$BRANDING_ENABLED" = "true" ]; then
  echo "Subscribe overlay: enabled (asset=$ASSET_PATH chromakey=$CHROMA_COLOR sim=$CHROMA_SIM blend=$CHROMA_BLEND)"

  ffmpeg -y \
    -stream_loop -1 -i "$VIDEO_LOOP" \
    -stream_loop -1 -i "$AUDIO_TRACK" \
    -i "$ASSET_ABS" \
    -t "$TARGET_SECONDS" \
    -filter_complex "\
      [2:v]chromakey=${CHROMA_COLOR}:${CHROMA_SIM}:${CHROMA_BLEND},despill=type=green:mix=${DESPILL_MIX},fade=t=out:st=${ALPHA_FADE_START}:d=${ALPHA_FADE_DUR}:alpha=1[sub]; \
      [0:v]fade=t=in:st=0:d=${FADE_DUR},fade=t=out:st=$((TARGET_SECONDS - FADE_DUR)):d=${FADE_DUR}[vbase]; \
      [vbase][sub]overlay=0:0:eof_action=pass[v]; \
      [1:a]afade=t=in:st=0:d=${FADE_DUR},afade=t=out:st=$((TARGET_SECONDS - FADE_DUR)):d=${FADE_DUR}[amain]; \
      [2:a]volume=${AUDIO_MIX_VOLUME}[asub]; \
      [amain][asub]amix=inputs=2:duration=first:dropout_transition=0[a]" \
    -map "[v]" -map "[a]" \
    -c:v libx264 -preset veryfast -crf 23 -c:a aac -b:a 160k \
    "$OUTPUT"
else
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
fi

ACTUAL_DURATION=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$OUTPUT")
echo "Assembled loop: target=${TARGET_SECONDS}s actual=${ACTUAL_DURATION}s -> $OUTPUT"
