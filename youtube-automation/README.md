# @makeitmanifest — Autonomous YouTube Automation

A no-human-approval content pipeline for a motivational-luxury faceless YouTube channel, split into a short-form pipeline, a long-form pipeline, and one orchestrator (Agent 0) that runs both. See `config/channel.json` for the full audience/niche/schedule spec this was built against.

## Status

| Piece | Status |
|---|---|
| Short-form source clips (48/58) | Done — `assets/short-form-clips/raw/` |
| Config + gate definitions | Done — `config/` |
| State scaffolding | Done — `state/` |
| Agent specs (0, 1.1-4.1, 1.2-6) | Done — `agents/` |
| Helper scripts (ffmpeg, YouTube upload) | Done — `scripts/` (untested end-to-end; ffmpeg/pip deps must be present in whatever session runs a cycle) |
| YouTube API credentials | **Blocked on you** — see `setup/YOUTUBE_API_SETUP.md` |
| CC0 audio library | Empty — Agent 4.2 populates it on first real run |
| Nano Banana image generation | Available via the `banana` skill already in this environment, no setup needed |
| Scheduled cloud routines (cron) | Not yet created — waiting on YouTube credentials so Agent 4.1/6 aren't blocked immediately |

## Architecture

```
Agent 0 (Orchestrator)
├── Short-form pipeline (fires 3x/day)
│   ├── 1.1 Trend Scout      → finds trending angles/titles/caption styles
│   ├── 2.1 Scriptwriter     → script + title + SEO + sound direction brief
│   ├── 3.1 Producer         → transforms a raw clip into a finished short
│   └── 4.1 Publisher        → uploads via YouTube Data API
└── Long-form pipeline (fires 1x/day)
    ├── 1.2 Format Scout     → studies competitor aesthetic/sound/SEO
    ├── 2.2 Image Sourcer    → generates a background image (Nano Banana)
    ├── 3.2 Animator         → adds subtle ambient motion, seamless loop
    ├── 4.2 Sound Sourcer    → verified CC0 ambient/phonk track
    ├── 5 Assembler          → mux + loop to 60-600 minutes
    └── 6 Publisher          → uploads via YouTube Data API
```

Plus a weekly analytics cycle (also owned by Agent 0) that reads back performance from `state/posted_history.json` and biases future scouting.

## Why no Pinterest scraping / no manual copyright bypass

Two ToS/copyright decisions were made deliberately, not by default:

- **Long-form background images** are generated fresh via Nano Banana, not scraped from Pinterest (which has no API for this and forbids bulk scraping in its ToS). Zero copyright exposure by construction.
- **Long-form audio** only comes from verified CC0/no-attribution-required sources, with the license checked at the source page — not just trusted from a prompt or a platform tag. See `agents/long_form/4.2_sound_sourcer.md`.
- **Short-form source clips** are a deliberate exception: the channel owner explicitly accepted the risk of using third-party-sourced clips, on the condition that Agent 3.1 actually transforms every clip (reframe, speed/color change, text overlay, audio replacement) before publish — see `assets/short-form-clips/raw/README.md` and `config/gates.json` → `short_form_gates`. This is documented, not silently skipped.

## Gate philosophy

`config/gates.json` defines every automatic gate (factual/controversy, platform policy, QA, copyright/license where applicable). **Gates are never lowered to hit the publishing schedule.** A failing item is quarantined in `state/quarantine.json` with the reason, and Agent 0 moves on to the next candidate. See `agents/0_orchestrator.md` for the full cycle logic.

## What's left before this runs autonomously

1. **You**: complete `setup/YOUTUBE_API_SETUP.md` (10 minutes, your Google login, free — no paid API).
2. **Me**: once credentials exist, verify `scripts/youtube_auth.py` / `scripts/youtube_upload.py` work end-to-end, then create the scheduled Claude Code cloud routines (3x/day short-form, 1x/day long-form, weekly analytics) that fire Agent 0.
3. **Both**: run one full cycle of each pipeline manually first to sanity-check output quality before trusting the schedule unattended.
