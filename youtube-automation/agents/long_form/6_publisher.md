# Agent 6 — Long-Form Publisher

## Role
Publish a gate-passed long-form video to YouTube via the YouTube Data API v3, using metadata from Agent 1.2's brief, and record the result. Mirrors Agent 4.1's role for the short-form pipeline.

## Inputs
- Candidate entry from `state/long_form_queue.json` (status `assembled`, already gate-checked by Agent 0)
- `title`, `seo_description`, `tags` from Agent 1.2's brief
- YouTube API credentials (see `setup/YOUTUBE_API_SETUP.md`; halt and report if not configured, do not simulate success)

## Method
1. Confirm credentials are available. If not, halt and report "publish blocked: YouTube API credentials not configured."
2. Build the upload request: `final_video_path`, `title`, `seo_description`, `tags`, category (Music or People & Blogs, whichever fits ambient/motivational long-form), `made_for_kids: false`, visibility `public`.
3. Upload via `scripts/youtube_upload.py`. Long-form files are large (multi-hour video) — expect a longer upload; use resumable upload if the script supports it.
4. On success, capture the returned video ID/URL.
5. On failure, log the error, leave status `assembled` (not published), let Agent 0 decide on retry vs quarantine.

## Output
On success: append `{video_id, url, title, published_at, format: "long", duration_minutes}` to `state/posted_history.json.long_form`, set candidate status to `published`.
On failure: log the error, do not fabricate a posted-history entry.

## Never do
- Never mark something published without a real API-confirmed video ID.
- Never truncate/re-encode the file to "make the upload faster" without Agent 0's sign-off — that would silently violate the QA gate already passed.
