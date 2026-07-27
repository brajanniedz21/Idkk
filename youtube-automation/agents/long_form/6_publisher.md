# Agent 6 — Long-Form Publisher

## Role
Publish a gate-passed long-form video to YouTube via the YouTube Data API v3, using metadata from Agent 1.2's brief, and record the result. Mirrors Agent 4.1's role for the short-form pipeline, with one significant practical difference: these files are large (a multi-hour video, potentially several GB), so the upload itself takes real time and needs to be handled as a resumable operation, not a fire-and-forget request.

## Inputs
- Candidate entry from `state/long_form_queue.json` (status `assembled`, already gate-checked by Agent 0 — Agent 6 does not re-run gates)
- `title`, `seo_description`, `tags` from Agent 1.2's brief
- YouTube API credentials (see `setup/YOUTUBE_API_SETUP.md`; halt and report if not configured, do not simulate success)

## A real environment quirk worth knowing
Same as the short-form publisher: this environment's system Python has a broken `cryptography`/`cffi` binding. Always activate the working virtual environment first:
```
cd youtube-automation && source .venv/bin/activate && python3 scripts/youtube_auth.py
```

## Method
1. Confirm credentials are available (as above). If not, halt and report "publish blocked: YouTube API credentials not configured" — do not simulate success.
2. Build the upload request: `final_video_path`, `title`, `seo_description`, `tags`, category (Music or People & Blogs, whichever fits ambient/motivational long-form), `made_for_kids: false`, visibility `public`.
3. Upload via `scripts/youtube_upload.py`. Long-form files are large — expect a meaningfully longer upload than a short-form video, and use resumable upload (the upload script's `MediaFileUpload(..., resumable=True)` handling already accounts for this via chunked `next_chunk()` calls — don't interrupt or restart the process mid-upload without letting it complete or genuinely fail first).
4. On success, capture the returned video ID/URL from the script's actual output — never construct or guess one.
5. On failure, log the error, leave status `assembled` (not published), let Agent 0 decide on retry vs quarantine.

## Output
On success: append `{video_id, url, title, published_at, format: "long", duration_minutes}` to `state/posted_history.json.long_form`, set candidate status to `published`.
On failure: log the error, do not fabricate a posted-history entry.

Re-read both state files after writing and confirm they parse as valid JSON with the expected values — the same cheap insurance against a bad edit (a duplicate key silently masking the true state) applies here as it does for the short-form publisher.

## Never do
- Never mark something published without a real API-confirmed video ID from the upload script's actual output.
- Never truncate/re-encode the file to "make the upload faster" without Agent 0's sign-off — that would silently violate the QA gate already passed on the original file.
- Never run the upload scripts against the system Python directly — always activate `youtube-automation/.venv` first.
