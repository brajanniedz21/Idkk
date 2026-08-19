#!/usr/bin/env python3
"""Build a seamlessly-loopable segment from a long-form source clip, using
whichever construction method the motion decision (scripts/motion_decision.py)
selected.

Two methods, gated by the intelligent loop-method selector (owner direction,
2026-08-01):

  reverse   — the original ping-pong-with-speed-ramp recipe (owner-approved,
              finalized 2026-07-29, see agents/long_form/3.2_animator.md).
              Preserved exactly as-is; this is not a rewrite, just lifted out
              of the per-cycle "build it by hand" recipe into a reusable
              script so the selector has something concrete to call.
  crossfade — new: a direct video dissolve loop for ambient-only clips where
              reversing would make particles/light visibly move backwards.

Both methods output a silent, 1920x1080 loop segment at the same encoding
settings, so scripts/ffmpeg_loop.sh (which just -stream_loops whatever it's
given) needs no changes to consume either one.

Usage:
  python3 loop_builder.py --input clip.mp4 --output loop_segment.mp4 --method reverse
  python3 loop_builder.py --input clip.mp4 --output loop_segment.mp4 --method crossfade
  # Optionally --decision <motion_decision.json> to print the required log block.
"""
import argparse
import subprocess
import sys

from motion_decision import load_decision, format_log_line

ENCODE_ARGS = ["-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p"]


def get_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def build_reverse_loop(input_path, output_path,
                        ramp_duration=1.5, ramp_steps=5,
                        ramp_factors=(1.0, 1.2, 1.45, 1.75, 2.2)):
    """Ping-pong loop with a deceleration ramp into the turnaround.

    Unchanged from the existing recipe: ramp the clip's last ~1.5s into
    progressively slower chunks, reverse that same ramped clip, concatenate
    forward+reversed. Both loop points are exact frame matches (the forward
    clip's last frame == the reversed clip's first frame, and vice versa),
    so no crossfade is needed here — that's what makes this method safe for
    clips with real subject/camera motion, where a crossfade would ghost.
    """
    duration = get_duration(input_path)
    ramp_start = max(0.0, duration - ramp_duration)
    step_len = (duration - ramp_start) / ramp_steps

    filters = [f"[0:v]trim=0:{ramp_start:.3f},setpts=PTS-STARTPTS[main]"]
    labels = ["main"]
    for i, factor in enumerate(ramp_factors[:ramp_steps]):
        a = ramp_start + i * step_len
        b = ramp_start + (i + 1) * step_len
        label = f"r{i}"
        filters.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=(PTS-STARTPTS)*{factor}[{label}]")
        labels.append(label)

    concat_inputs = "".join(f"[{l}]" for l in labels)
    filters.append(f"{concat_inputs}concat=n={len(labels)}:v=1:a=0[ramped]")
    filters.append("[ramped]scale=1920:1080:flags=lanczos,format=yuv420p,split[fwd][rev0]")
    filters.append("[rev0]reverse[rev]")
    filters.append("[fwd][rev]concat=n=2:v=1:a=0[v]")
    filter_complex = ";".join(filters)

    cmd = ["ffmpeg", "-y", "-i", input_path, "-filter_complex", filter_complex,
           "-map", "[v]"] + ENCODE_ARGS + [output_path]
    subprocess.run(cmd, check=True)
    return output_path


def build_crossfade_loop(input_path, output_path, min_clean_middle=0.2):
    """Direct-dissolve loop for ambient-only clips (no black, no hard cut).

    Crossfade duration: min(2.0, max(0.6, source_duration * 0.12)).

    Construction (a genuinely repeatable loop unit, not just a dissolve
    stitched onto two copies with a hard cut elsewhere):
      - incoming = clip[0 : X]           (set aside as the blend target)
      - middle   = clip[X : D-X]         (played normally, no effect)
      - outgoing = clip[D-X : D]         (the tail)
      - blend    = dissolve(outgoing -> incoming), duration X, no black
      - loop unit = middle + blend

    The blend's last frame lands on ~the same content as the loop unit's
    first frame (incoming's tail == middle's start), so repeating the loop
    unit wraps with a soft dissolve at exactly the point the next repetition
    begins — never a hard cut, never a frozen/black frame.
    """
    duration = get_duration(input_path)
    crossfade_dur = min(2.0, max(0.6, duration * 0.12))

    # Never let the crossfade eat so much of the clip that no clean middle
    # footage is left — shrink it instead of producing a degenerate loop.
    max_crossfade = (duration - min_clean_middle) / 2
    if max_crossfade < crossfade_dur:
        crossfade_dur = max(0.05, max_crossfade)
    if crossfade_dur <= 0:
        raise ValueError(
            f"source clip too short ({duration:.2f}s) for a crossfade loop "
            f"with a clean middle section — use reverse instead"
        )

    X = crossfade_dur
    mid_end = duration - X

    filters = [
        f"[0:v]trim={X:.3f}:{mid_end:.3f},setpts=PTS-STARTPTS[mid]",
        f"[0:v]trim={mid_end:.3f}:{duration:.3f},setpts=PTS-STARTPTS[outg]",
        f"[0:v]trim=0:{X:.3f},setpts=PTS-STARTPTS[inc]",
        f"[outg][inc]xfade=transition=fade:duration={X:.3f}:offset=0[blend]",
        "[mid][blend]concat=n=2:v=1:a=0[cat]",
        "[cat]scale=1920:1080:flags=lanczos,format=yuv420p[v]",
    ]
    filter_complex = ";".join(filters)

    cmd = ["ffmpeg", "-y", "-i", input_path, "-filter_complex", filter_complex,
           "-map", "[v]"] + ENCODE_ARGS + [output_path]
    subprocess.run(cmd, check=True)
    return output_path


METHODS = {
    "reverse": build_reverse_loop,
    "crossfade": build_crossfade_loop,
}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--method", required=True, choices=list(METHODS))
    parser.add_argument("--decision", default=None,
                         help="Path to a motion_decision.json to print as the required log block "
                              "before building (schema-validated first).")
    args = parser.parse_args()

    try:
        if args.decision:
            decision = load_decision(args.decision)
            if decision["loop_method"] != args.method:
                print(
                    f"WARNING: decision file says loop_method={decision['loop_method']!r} "
                    f"but --method={args.method!r} was passed; building with --method as given.",
                    file=sys.stderr,
                )
            print(format_log_line(decision))

        build_fn = METHODS[args.method]
        out = build_fn(args.input, args.output)
        duration = get_duration(out)
        print(f"Loop segment built: method={args.method} duration={duration:.3f}s -> {out}")
    except Exception as e:
        print(f"LOOP BUILD FAILED: {e}", file=sys.stderr)
        sys.exit(1)
