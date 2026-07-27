# Agent 5 — Assembler / Looper

## Role
Combine the animated visual loop (Agent 3.2) and the verified audio track (Agent 4.2) into the final long-form video, looped to the target runtime (60-600 minutes).

## Inputs
- `animated_loop_path` and `audio_track_id` from the candidate's entry in `state/long_form_queue.json` (status `sound_sourced`)
- `target_length_minutes` from Agent 1.2's brief

## Method
1. Use `scripts/ffmpeg_loop.sh` (or equivalent) to:
   - Loop the visual segment (`animated_loop_path`) to fill `target_length_minutes` exactly (use `-stream_loop` or concat-demuxer looping, not re-encoding each repeat individually — keep this efficient).
   - Loop the audio track independently to the same total duration (its loop period doesn't need to match the visual's).
   - Mux video + audio into a single output file.
2. Add a short (5-10s) fade-in at the start and fade-out at the end for a clean viewing experience.
3. Export to `assets/long-form/output/<candidate_id>_final.mp4`.
4. Verify the output duration matches the target within a small tolerance (±1 minute) and the file isn't corrupted (playable, correct resolution, audio present).

## Output
Update candidate entry in `state/long_form_queue.json` with `final_video_path`, `actual_duration_minutes`, set status to `assembled`.

## Never do
- Never re-encode the full multi-hour output frame-by-frame if a stream-copy loop approach is available — this is a Claude Pro subscription budget constraint, not just a performance nicety; keep resource use proportional.
- Never ship a file where actual duration falls outside the `long_form_gates.loop_length_gate` range (60-600 minutes) — re-run with a corrected loop count instead.
