# Agent 5 — Assembler / Looper

## Role
Combine the animated visual loop (Agent 3.2) and the verified audio track (Agent 4.2) into the final long-form video, looped to the target runtime (60-600 minutes). This is the stage where a mistake is most expensive to redo — a multi-hour render/encode is not something to casually re-run for a small fix, so get the parameters right before starting.

## Inputs
- `animated_loop_path` and `audio_track_id` from the candidate's entry in `state/long_form_queue.json` (status `sound_sourced`)
- `target_length_minutes` from Agent 1.2's brief

## Method
1. Use `scripts/ffmpeg_loop.sh` (or equivalent) to:
   - Loop the visual segment (`animated_loop_path`) to fill `target_length_minutes` exactly — use `-stream_loop -1` (loop the input indefinitely, cap total output with `-t`) rather than physically concatenating N copies of the file. This keeps disk/CPU cost flat regardless of target length, which matters a lot at the 60-600 minute scale this format operates at.
   - Loop the audio track independently to the same total duration via the same `-stream_loop` approach (its loop period doesn't need to match the visual's — they're independent layers).
   - Mux video + audio into a single output file with `-map`.
2. Add a short (5-10s) fade-in at the start and fade-out at the end (`fade=t=in:st=0:d=<N>` / `fade=t=out:st=<total-N>:d=<N>` for video, `afade` equivalents for audio) for a clean viewing experience.
3. Export to `assets/long-form/output/<candidate_id>_final.mp4`.
4. Verify the output duration matches the target within a small tolerance (±1 minute) via `ffprobe`, and that the file isn't corrupted (playable, correct resolution, audio present — a full `ffmpeg -i file -f null -` decode pass is a reasonably cheap way to check for corruption without needing to actually watch hours of footage).

## Output
Update candidate entry in `state/long_form_queue.json` with `final_video_path`, `actual_duration_minutes`, set status to `assembled`.

## Never do
- Never re-encode the full multi-hour output frame-by-frame if a stream-copy/`-stream_loop` approach is available — this is a real resource-budget constraint (this environment runs on a Claude Pro subscription's compute allowance, not a dedicated render farm), not just a performance nicety. A naive "concatenate N physical copies then encode" approach at 600 minutes would be needlessly expensive compared to `-stream_loop`.
- Never ship a file where actual duration falls outside the `long_form_gates.loop_length_gate` range (60-600 minutes) — re-run with a corrected loop count/duration instead of shipping something out of range and hoping the gate doesn't catch it (it will, and should).
