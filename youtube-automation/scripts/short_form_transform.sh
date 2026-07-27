#!/usr/bin/env bash
# Apply Agent 3.1's mandatory transform checklist to 1-3 raw short-form clips,
# producing a FAST-CUT vertical short: reframe to vertical, dark/low-exposure
# grade, quick cuts (not one long slowed shot), burned-in text sized to
# actually fit the frame, and full audio replacement.
#
# Per config/channel.json short_form_style_guidance: short-form must be
# high-energy/fast-paced (a cut or text change every ~1.5-3s), dark/moody
# low-exposure grade, and use upbeat/fast-tempo CC0 audio — never the calm
# ambient tracks reserved for long-form.
#
# Usage:
#   short_form_transform.sh <output_clip> <cc0_audio_track> <duration_seconds> \
#     <clip1> <clip2> [clip3...] -- <text1> [text2] [text3...]
#
# Splits the target duration evenly across the given clips (fast cuts, one
# segment per clip) and one text beat per segment (extra text args beyond
# the clip count are ignored; fewer text args than clips leaves later
# segments untexted). Text is auto font-sized down for long lines so it
# never overflows the 1080px frame width.

set -euo pipefail

OUTPUT="$1"; shift
AUDIO="$1"; shift
DURATION="$1"; shift

CLIPS=()
while [ "$1" != "--" ]; do
  CLIPS+=("$1")
  shift
done
shift # consume --

TEXTS=("$@")

NUM_CLIPS=${#CLIPS[@]}
SEG_DUR=$(python3 -c "print(round(${DURATION}/${NUM_CLIPS}, 3))")

# Max characters per line before we shrink the font, tuned for a 1080px
# frame with ~40px side margin using a bold serif-ish font.
MAX_CHARS_PER_LINE=22
DEFAULT_FONTSIZE=52
MIN_FONTSIZE=34

font_size_for_text() {
  local text="$1"
  local longest_line=0
  while IFS= read -r line; do
    local len=${#line}
    [ "$len" -gt "$longest_line" ] && longest_line=$len
  done <<< "$text"
  if [ "$longest_line" -le "$MAX_CHARS_PER_LINE" ]; then
    echo "$DEFAULT_FONTSIZE"
  else
    # scale down proportionally, floor at MIN_FONTSIZE
    local scaled=$(( DEFAULT_FONTSIZE * MAX_CHARS_PER_LINE / longest_line ))
    [ "$scaled" -lt "$MIN_FONTSIZE" ] && scaled=$MIN_FONTSIZE
    echo "$scaled"
  fi
}

INPUT_ARGS=()
for c in "${CLIPS[@]}"; do
  INPUT_ARGS+=(-i "$c")
done
INPUT_ARGS+=(-i "$AUDIO")
AUDIO_IDX=$NUM_CLIPS

# Text is written to temp files and referenced via drawtext's textfile= option
# rather than inline text=, so apostrophes/colons/quotes in the copy never
# need filtergraph-level escaping (a real, previously-hit failure mode).
TEXTFILE_DIR=$(mktemp -d)
trap 'rm -rf "$TEXTFILE_DIR"' EXIT

FILTER=""
CONCAT_INPUTS=""
for i in "${!CLIPS[@]}"; do
  TEXT="${TEXTS[$i]:-}"
  FONTSIZE=$(font_size_for_text "$TEXT")

  DRAWTEXT=""
  if [ -n "$TEXT" ]; then
    TEXTFILE="${TEXTFILE_DIR}/text_${i}.txt"
    printf '%b' "$TEXT" > "$TEXTFILE"
    DRAWTEXT=",drawtext=textfile='${TEXTFILE}':fontcolor=white:fontsize=${FONTSIZE}:box=1:boxcolor=black@0.45:boxborderw=18:x=(w-text_w)/2:y=h*0.74:line_spacing=8"
  fi

  # Dark/low-exposure "gymcore" grade: reduced brightness/exposure, boosted
  # contrast, slight desaturation/cool tone, mild vignette for mood.
  FILTER+="[${i}:v]trim=0:${SEG_DUR},setpts=PTS-STARTPTS,\
crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920,\
eq=contrast=1.20:saturation=0.88:brightness=-0.09:gamma=0.92,\
vignette=PI/4${DRAWTEXT}[v${i}]; "
  CONCAT_INPUTS+="[v${i}]"
done

FILTER+="${CONCAT_INPUTS}concat=n=${NUM_CLIPS}:v=1:a=0[vout]; "
FILTER+="[${AUDIO_IDX}:a]atrim=0:${DURATION},asetpts=PTS-STARTPTS,volume=1.0[a]"

ffmpeg -y "${INPUT_ARGS[@]}" \
  -filter_complex "$FILTER" \
  -map "[vout]" -map "[a]" \
  -t "$DURATION" \
  -c:v libx264 -preset medium -crf 20 -c:a aac -b:a 192k \
  "$OUTPUT"

echo "Transformed (fast-cut): ${NUM_CLIPS} clips x ~${SEG_DUR}s -> vertical, dark/low-exposure grade, per-segment text, audio-replaced -> $OUTPUT"
