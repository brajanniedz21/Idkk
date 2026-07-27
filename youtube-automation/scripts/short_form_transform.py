#!/usr/bin/env python3
"""Apply Agent 3.1's mandatory transform checklist producing a FAST-CUT
vertical short: reframe to vertical, dark/low-exposure grade, quick cuts
(each individual shot capped at 2.0s max, per real competitor research —
see state/performance_notes.json), burned-in text sized to fit the frame,
and full audio replacement.

Per config/channel.json short_form_style_guidance: short-form must be
high-energy/fast-paced, dark/moody low-exposure grade, upbeat/fast-tempo
CC0 audio only.

Usage:
  short_form_transform.py --output OUT.mp4 --audio TRACK.mp3 --duration 27 \
    --clips raw/38.mp4 raw/9.mp4 raw/37.mp4 raw/53.mp4 raw/8.mp4 \
    --texts "BEAT ONE TEXT" "BEAT TWO TEXT" ...

`--clips` is the pool of source clips (as many distinct ones as you have
that fit the visual_direction — more is better for variety). `--texts` is
the list of on-screen text BEATS (fewer, longer than the cut count is
fine/expected — each beat spans multiple quick cuts so it stays readable
while the visuals still cut every <=2s). The script:
  1. Splits total duration into shots of <=2.0s each (more shots than you
     have clips is fine — clips are reused with a rotating start-offset so
     repeats don't show the identical frame each time).
  2. Assigns each shot's on-screen text from whichever text beat's time
     window it falls into.
  3. Applies the dark/low-exposure grade to every shot.
  4. Concats all shots, replaces audio entirely with the given CC0 track.
"""
import argparse
import math
import subprocess
import tempfile
import os
import sys

MAX_SHOT_SECONDS = 2.0
MAX_CHARS_PER_LINE = 22
DEFAULT_FONTSIZE = 52
MIN_FONTSIZE = 34


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def font_size_for_text(text):
    if not text:
        return DEFAULT_FONTSIZE
    longest = max(len(line) for line in text.replace("\\n", "\n").split("\n"))
    if longest <= MAX_CHARS_PER_LINE:
        return DEFAULT_FONTSIZE
    scaled = int(DEFAULT_FONTSIZE * MAX_CHARS_PER_LINE / longest)
    return max(scaled, MIN_FONTSIZE)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--clips", nargs="+", required=True)
    ap.add_argument("--texts", nargs="*", default=[])
    args = ap.parse_args()

    duration = args.duration
    clips = args.clips
    texts = args.texts or [""]

    num_shots = max(1, math.ceil(duration / MAX_SHOT_SECONDS))
    shot_dur = round(duration / num_shots, 3)
    beat_dur = duration / len(texts)

    clip_durations = {c: ffprobe_duration(c) for c in set(clips)}
    reuse_count = {c: 0 for c in clips}

    with tempfile.TemporaryDirectory() as textdir:
        input_args = []
        for c in clips:
            pass
        filter_parts = []
        concat_labels = ""
        shot_input_idx = []

        for i in range(num_shots):
            clip = clips[i % len(clips)]
            shot_input_idx.append(clip)

        # ffmpeg -i args: one per shot (simplest correctness-first approach;
        # duplicate -i for a reused clip is fine, ffmpeg handles it, and it
        # lets each reused instance seek to a different start offset).
        input_args = []
        for clip in shot_input_idx:
            input_args += ["-i", clip]
        input_args += ["-i", args.audio]
        audio_idx = len(shot_input_idx)

        clip_repeat_seen = {}
        for i, clip in enumerate(shot_input_idx):
            seen = clip_repeat_seen.get(clip, 0)
            clip_repeat_seen[clip] = seen + 1
            cdur = clip_durations[clip]
            start = (seen * shot_dur) % max(cdur - shot_dur, 0.01)

            shot_center_time = (i + 0.5) * shot_dur
            beat_index = min(int(shot_center_time / beat_dur), len(texts) - 1)
            text = texts[beat_index]
            fontsize = font_size_for_text(text)

            drawtext = ""
            if text:
                textfile = os.path.join(textdir, f"text_{i}.txt")
                with open(textfile, "w") as f:
                    # Accept a literal two-character "\n" (common when text
                    # arrives via shell double-quotes, which don't expand
                    # it) as well as a real newline character.
                    f.write(text.replace("\\n", "\n"))
                drawtext = (
                    f",drawtext=textfile='{textfile}':fontcolor=white:"
                    f"fontsize={fontsize}:box=1:boxcolor=black@0.45:"
                    f"boxborderw=18:x=(w-text_w)/2:y=h*0.74:line_spacing=8"
                )

            filter_parts.append(
                f"[{i}:v]trim={start:.3f}:{start + shot_dur:.3f},"
                f"setpts=PTS-STARTPTS,"
                f"crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920,"
                f"eq=contrast=1.20:saturation=0.88:brightness=-0.09:gamma=0.92,"
                f"vignette=PI/4{drawtext}[v{i}]"
            )
            concat_labels += f"[v{i}]"

        filter_complex = "; ".join(filter_parts)
        filter_complex += f"; {concat_labels}concat=n={num_shots}:v=1:a=0[vout]"
        filter_complex += (
            f"; [{audio_idx}:a]atrim=0:{duration},asetpts=PTS-STARTPTS,"
            f"volume=1.0[a]"
        )

        cmd = [
            "ffmpeg", "-y", *input_args,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[a]",
            "-t", str(duration),
            "-c:v", "libx264", "-preset", "medium", "-crf", "20",
            "-c:a", "aac", "-b:a", "192k",
            args.output,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(result.stderr[-4000:], file=sys.stderr)
            sys.exit(1)

    print(
        f"Transformed (fast-cut, <=2s shots): {num_shots} shots from "
        f"{len(set(clips))} distinct clips x ~{shot_dur:.2f}s -> vertical, "
        f"dark/low-exposure grade, per-beat text, audio-replaced -> {args.output}"
    )


if __name__ == "__main__":
    main()
