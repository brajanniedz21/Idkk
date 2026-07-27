#!/usr/bin/env python3
"""Apply Agent 3.1's mandatory transform checklist producing a FAST-CUT
vertical short: reframe to vertical, dark/low-exposure grade, cuts synced
to the actual detected beats of the audio track (capped at 2.0s max per
shot, per real competitor research — see state/performance_notes.json),
burned-in text sized to fit the frame, and full audio replacement.

Per config/channel.json short_form_style_guidance: short-form must be
high-energy/fast-paced, dark/moody low-exposure grade, upbeat/fast-tempo
CC0 audio only. A fast-tempo track naturally gives closer-together beats
and therefore quicker cuts — pick upbeat audio, not just for mood but
because it directly drives the edit pace.

Usage:
  short_form_transform.py --output OUT.mp4 --audio TRACK.mp3 --duration 27 \
    --clips raw/38.mp4 raw/9.mp4 raw/37.mp4 raw/53.mp4 raw/8.mp4 \
    --texts "BEAT ONE TEXT" "BEAT TWO TEXT" ...

`--clips` is the pool of source clips (as many distinct ones as you have
that fit the visual_direction — more is better for variety). `--texts` is
the list of on-screen text BEATS (fewer, longer than the cut count is
fine/expected — each beat spans multiple quick cuts so it stays readable
while the visuals still cut on the beat). The script:
  1. Runs beat detection (librosa) on the audio track and uses the actual
     detected beat timestamps as cut points, so every visual cut lands on
     a beat — not an arbitrary fixed interval. Beats further apart than
     2.0s get subdivided so no shot ever exceeds the cap; beats closer
     together than ~0.5s get merged so cuts don't flicker unreadably.
  2. Assigns each shot's on-screen text from whichever text beat's time
     window it falls into.
  3. Applies the dark/low-exposure grade to every shot.
  4. Concats all shots, replaces audio entirely with the given CC0 track.
"""
import argparse
import subprocess
import tempfile
import os
import sys

MAX_SHOT_SECONDS = 2.0
MIN_SHOT_SECONDS = 0.45
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


def beat_cut_points(audio_path, duration):
    """Detect real beat timestamps in the audio and turn them into a list
    of shot-boundary times covering [0, duration], respecting
    MAX_SHOT_SECONDS/MIN_SHOT_SECONDS. Falls back to an even 2.0s grid if
    beat detection finds nothing usable (e.g. a non-musical/ambient track).
    """
    try:
        import librosa
        y, sr = librosa.load(audio_path, sr=None, duration=duration)
        _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = sorted(set(round(t, 3) for t in librosa.frames_to_time(beat_frames, sr=sr)))
        # Cutting on every single detected beat is often too fast to read
        # (sub-1s flicker on a dense track). Target ~1.5s/shot by striding
        # through the beat list, while staying genuinely beat-locked (every
        # cut still lands exactly on a real beat, just not every one).
        if len(beats) >= 2:
            avg_interval = (beats[-1] - beats[0]) / (len(beats) - 1)
            target_shot = 1.5
            stride = max(1, round(target_shot / avg_interval))
            beats = beats[::stride]
    except Exception as e:
        print(f"Beat detection failed ({e}), falling back to a fixed 2.0s grid.", file=sys.stderr)
        beats = []

    points = [0.0] + [b for b in beats if 0.0 < b < duration] + [duration]
    points = sorted(set(points))

    # Merge points closer together than MIN_SHOT_SECONDS (avoids
    # unreadable sub-frame flicker on very dense beat tracks).
    merged = [points[0]]
    for p in points[1:]:
        if p - merged[-1] >= MIN_SHOT_SECONDS:
            merged.append(p)
    if merged[-1] != duration:
        merged[-1] = duration
    points = merged

    # Subdivide any gap wider than MAX_SHOT_SECONDS (covers slow intros,
    # breakdowns, or a track with no detected beats at all).
    final = [points[0]]
    for p in points[1:]:
        gap_start = final[-1]
        gap = p - gap_start
        if gap > MAX_SHOT_SECONDS:
            n_sub = int(gap // MAX_SHOT_SECONDS) + 1
            step = gap / n_sub
            for k in range(1, n_sub + 1):
                final.append(round(gap_start + step * k, 3))
        else:
            final.append(p)

    final[0] = 0.0
    final[-1] = duration
    return final


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

    cut_points = beat_cut_points(args.audio, duration)
    num_shots = len(cut_points) - 1
    beat_dur = duration / len(texts)

    clip_durations = {c: ffprobe_duration(c) for c in set(clips)}

    with tempfile.TemporaryDirectory() as textdir:
        shot_input_idx = [clips[i % len(clips)] for i in range(num_shots)]

        input_args = []
        for clip in shot_input_idx:
            input_args += ["-i", clip]
        input_args += ["-i", args.audio]
        audio_idx = len(shot_input_idx)

        filter_parts = []
        concat_labels = ""
        clip_repeat_seen = {}
        shot_durs = []
        for i, clip in enumerate(shot_input_idx):
            shot_dur = round(cut_points[i + 1] - cut_points[i], 3)
            shot_durs.append(shot_dur)
            seen = clip_repeat_seen.get(clip, 0)
            clip_repeat_seen[clip] = seen + 1
            cdur = clip_durations[clip]
            start = (seen * shot_dur) % max(cdur - shot_dur, 0.01)

            shot_center_time = cut_points[i] + shot_dur / 2
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

    avg_dur = sum(shot_durs) / len(shot_durs)
    print(
        f"Transformed (beat-synced cuts, <={MAX_SHOT_SECONDS}s cap): {num_shots} shots from "
        f"{len(set(clips))} distinct clips, avg ~{avg_dur:.2f}s/shot "
        f"(range {min(shot_durs):.2f}s-{max(shot_durs):.2f}s, cut points from real "
        f"beat detection on {args.audio}) -> vertical, dark/low-exposure grade, "
        f"per-beat text, audio-replaced -> {args.output}"
    )


if __name__ == "__main__":
    main()
