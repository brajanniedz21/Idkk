# Agent 5 — Assembler / Looper

## Role
Combine the animated visual loop (Agent 3.2) and the verified audio track (Agent 4.2) into the final long-form video, looped to the target runtime (60-600 minutes). This is the stage where a mistake is most expensive to redo — a multi-hour render/encode is not something to casually re-run for a small fix, so get the parameters right before starting.

## Inputs
- `animated_loop_path` and `audio_track_id` from the candidate's entry in `state/long_form_queue.json` (status `sound_sourced`)
- `target_length_minutes` from Agent 1.2's brief

## Method
1. Use `scripts/ffmpeg_loop.sh` (the canonical assembly script — do not hand-roll an equivalent ffmpeg command, it already includes step 2 below) to:
   - Loop the visual segment (`animated_loop_path`) to fill `target_length_minutes` exactly — use `-stream_loop -1` (loop the input indefinitely, cap total output with `-t`) rather than physically concatenating N copies of the file. This keeps disk/CPU cost flat regardless of target length, which matters a lot at the 60-600 minute scale this format operates at.
   - Loop the audio track independently to the same total duration via the same `-stream_loop` approach (its loop period doesn't need to match the visual's — they're independent layers).
   - Mux video + audio into a single output file with `-map`.
2. Add a short (5-10s) fade-in at the start and fade-out at the end (`fade=t=in:st=0:d=<N>` / `fade=t=out:st=<total-N>:d=<N>` for video, `afade` equivalents for audio) for a clean viewing experience.
   **Subscribe animation overlay (owner direction, 2026-08-01 — permanent, automatic):** `scripts/ffmpeg_loop.sh` composites the branding Subscribe animation (`config/branding.json.subscribe_animation`) on top of the opening scene starting at 00:00 whenever that config's `enabled` flag is true and `long_form` is in `applies_to_formats` — this happens automatically inside the script, Agent 5 does not need to do anything extra to trigger it. Every tunable value (asset path, chromakey color/similarity/blend, despill mix, fade-out timing, audio mix volume) lives in that one config file, not hard-coded in the script. What it does, mechanically: chroma-keys the green background out of the overlay asset, strips residual green edge-spill via `despill`, layers an alpha fade-out timed to the asset's own baked-in fade so no black rectangle is left behind, overlays it at full-frame with `eof_action=pass` (the overlay clip is fed without `-stream_loop`, so it plays exactly once regardless of how many times the underlying loop segment repeats), and mixes the overlay's own SFX audio under the ambient track via `amix` at the configured volume — never replacing or interrupting the ambience. This does not delay or alter the underlying video/audio's normal 00:00 start, and does not change the final target duration (the overlay is composited within the same `-t`-capped ffmpeg pass, not appended). If a future candidate should skip the overlay, that's a `config/branding.json` edit (or per-format `applies_to_formats` scoping), not a per-run flag to remember.
3. Export to `assets/long-form/output/<candidate_id>_final.mp4`.
4. Verify the output duration matches the target within a small tolerance (±1 minute) via `ffprobe`, and that the file isn't corrupted (playable, correct resolution, audio present — a full `ffmpeg -i file -f null -` decode pass is a reasonably cheap way to check for corruption without needing to actually watch hours of footage). If the Subscribe overlay was applied, also spot-check (via a couple of extracted frames, e.g. `ffmpeg -ss <t> -i <output> -vframes 1 <frame>.png`) that it appears cleanly at the start and is fully gone by ~4-5s in — a corrupted/misconfigured chromakey is a visible defect that duration/decode checks alone won't catch.

## Output
Update candidate entry in `state/long_form_queue.json` with `final_video_path`, `actual_duration_minutes`, set status to `assembled`.

## Never do
- Never re-encode the full multi-hour output frame-by-frame if a stream-copy/`-stream_loop` approach is available — this is a real resource-budget constraint (this environment runs on a Claude Pro subscription's compute allowance, not a dedicated render farm), not just a performance nicety. A naive "concatenate N physical copies then encode" approach at 600 minutes would be needlessly expensive compared to `-stream_loop`.
- Never ship a file where actual duration falls outside the `long_form_gates.loop_length_gate` range (60-600 minutes) — re-run with a corrected loop count/duration instead of shipping something out of range and hoping the gate doesn't catch it (it will, and should).
