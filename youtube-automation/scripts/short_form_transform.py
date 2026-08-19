#!/usr/bin/env python3
"""Apply Agent 3.1's mandatory transform checklist producing a FAST-CUT
vertical short: reframe to vertical, dark/low-exposure grade, cuts synced
to the actual detected beats of the audio track (capped at 1.5s max per
shot, per owner direction — see state/performance_notes.json), and full
audio replacement. No on-screen text/captions — owner decided these add
nothing and should be dropped (2026-07-27).

Per config/channel.json short_form_style_guidance: short-form must be
high-energy/fast-paced, dark/moody low-exposure grade, upbeat/fast-tempo
audio. A fast-tempo track naturally gives closer-together beats and
therefore quicker cuts — pick upbeat audio, not just for mood but
because it directly drives the edit pace.

The audio's own slow/quiet intro (before the beat/hook really kicks in)
is detected and skipped, so playback starts on the actual energetic part
of the song — matters because a viewer scrolling onto a Short should
land on the hook, not a quiet build-up.

Usage:
  short_form_transform.py --output OUT.mp4 --audio TRACK.mp3 --duration 27 \
    --clips raw/38.mp4 raw/9.mp4 raw/37.mp4 raw/53.mp4 raw/8.mp4

`--clips` is the pool of source clips (as many distinct ones as you have
that fit the visual_direction — more is better for variety). The script:
  1. Detects where the track's slow/quiet intro ends (RMS energy ramp-up)
     and trims it off, so the audio used starts on the real hook.
  2. Runs beat detection (librosa) on that trimmed audio and uses the
     actual detected beat timestamps as cut points, so every visual cut
     lands on a beat — not an arbitrary fixed interval. Beats further
     apart than 1.5s get subdivided so no shot ever exceeds the cap;
     beats closer together than ~0.45s get merged so cuts don't flicker
     unreadably.
  3. Applies the dark/low-exposure grade to every shot.
  4. Concats all shots, replaces audio entirely with the trimmed/looped
     track — no text overlays.
"""
import argparse
import subprocess
import tempfile
import os
import sys

MAX_SHOT_SECONDS = 1.5
MIN_SHOT_SECONDS = 0.45


def ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def detect_hook_offset(y, sr):
    """Find where the track's energy ramps up into its real hook/drop,
    so a slow/quiet intro can be skipped. Uses short-time RMS energy:
    finds the first time the RMS crosses ~65% of the track's sustained
    high-energy level and stays there for at least ~0.5s. Returns 0.0 if
    no clear ramp-up is found (e.g. the track is already high-energy from
    the start, or too short to have a meaningful intro).
    """
    import librosa
    import numpy as np

    hop_length = 512
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    times = librosa.frames_to_time(range(len(rms)), sr=sr, hop_length=hop_length)

    if len(rms) < 10:
        return 0.0

    # "Sustained high-energy level" = 75th percentile of RMS across the
    # whole track (robust to a single loud transient, unlike the max).
    high_level = float(np.percentile(rms, 75))
    threshold = 0.65 * high_level

    min_sustain_frames = max(1, int(0.5 * sr / hop_length))
    for i in range(len(rms) - min_sustain_frames):
        if rms[i] >= threshold and (rms[i:i + min_sustain_frames] >= threshold * 0.8).all():
            offset = float(times[i])
            # Don't skip more than half the track — a false-positive late
            # detection shouldn't eat most of the available audio.
            native_dur = len(y) / sr
            return offset if offset < native_dur * 0.5 else 0.0
    return 0.0


def trim_intro(audio_path, workdir):
    """Detect and cut the slow intro off, returning a path to a new,
    shorter audio file that starts on the real hook. Falls back to the
    original file untouched if detection fails or finds no offset.
    """
    try:
        import librosa
        y, sr = librosa.load(audio_path, sr=None)
        offset = detect_hook_offset(y, sr)
    except Exception as e:
        print(f"Hook-detection failed ({e}), using the track from its start.", file=sys.stderr)
        offset = 0.0

    if offset <= 0.05:
        return audio_path, 0.0

    trimmed_path = os.path.join(workdir, "trimmed_audio.mp3")
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{offset:.3f}", "-i", audio_path,
         "-c:a", "libmp3lame", "-q:a", "2", trimmed_path],
        capture_output=True, check=True,
    )
    return trimmed_path, offset


def beat_cut_points(audio_path, duration):
    """Detect real beat timestamps in the (already intro-trimmed) audio
    and turn them into a list of shot-boundary times covering
    [0, duration], respecting MAX_SHOT_SECONDS/MIN_SHOT_SECONDS. Falls
    back to an even 1.5s grid if beat detection finds nothing usable.
    """
    try:
        import librosa
        # Load the audio's own natural length (not capped to `duration`)
        # so we detect its real beat pattern, then tile that pattern to
        # cover the full target duration — matters when the source file is
        # shorter than the requested short (e.g. a ~15-20s trending-audio
        # excerpt looped via -stream_loop in the ffmpeg command below).
        y, sr = librosa.load(audio_path, sr=None)
        native_dur = len(y) / sr
        _, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        beats = sorted(set(round(t, 3) for t in librosa.frames_to_time(beat_frames, sr=sr)))
        # Cutting on every single detected beat is often too fast to read
        # (sub-1s flicker on a dense track). Target ~1.2s/shot by striding
        # through the beat list, while staying genuinely beat-locked (every
        # cut still lands exactly on a real beat, just not every one) and
        # comfortably under the new 1.5s hard cap.
        if len(beats) >= 2:
            avg_interval = (beats[-1] - beats[0]) / (len(beats) - 1)
            target_shot = 1.2
            stride = max(1, round(target_shot / avg_interval))
            beats = beats[::stride]
        if native_dur < duration and beats:
            tiled = []
            offset = 0.0
            while offset < duration:
                tiled.extend(b + offset for b in beats)
                offset += native_dur
            beats = tiled
    except Exception as e:
        print(f"Beat detection failed ({e}), falling back to a fixed 1.5s grid.", file=sys.stderr)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", required=True)
    ap.add_argument("--audio", required=True)
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--clips", nargs="+", required=True)
    args = ap.parse_args()

    duration = args.duration
    clips = args.clips

    clip_durations = {c: ffprobe_duration(c) for c in set(clips)}

    with tempfile.TemporaryDirectory() as workdir:
        trimmed_audio, intro_offset = trim_intro(args.audio, workdir)
        cut_points = beat_cut_points(trimmed_audio, duration)
        num_shots = len(cut_points) - 1

        shot_input_idx = [clips[i % len(clips)] for i in range(num_shots)]

        input_args = []
        for clip in shot_input_idx:
            input_args += ["-i", clip]
        # -stream_loop -1 loops the (intro-trimmed) audio input
        # indefinitely so short source clips (e.g. a ~15-20s TikTok
        # excerpt of a song) still fill the full target duration via the
        # atrim below, instead of leaving the tail silent.
        input_args += ["-stream_loop", "-1", "-i", trimmed_audio]
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

            filter_parts.append(
                f"[{i}:v]trim={start:.3f}:{start + shot_dur:.3f},"
                f"setpts=PTS-STARTPTS,"
                f"crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920,"
                f"eq=contrast=1.20:saturation=0.88:brightness=-0.09:gamma=0.92,"
                f"vignette=PI/4[v{i}]"
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
        f"(range {min(shot_durs):.2f}s-{max(shot_durs):.2f}s, intro skipped: {intro_offset:.2f}s, "
        f"cut points from real beat detection on {args.audio}) -> vertical, "
        f"dark/low-exposure grade, no captions, audio-replaced -> {args.output}"
    )


if __name__ == "__main__":
    main()
