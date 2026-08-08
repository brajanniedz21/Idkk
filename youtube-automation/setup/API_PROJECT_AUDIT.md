# YouTube API Project Audit

**Status:** P0 production requirement  
**Last verified:** [to be filled in by operator]  
**Next review:** Before first public production upload

## Problem

For API projects created after 2020-07-28, **unaudited uploads may be restricted to private viewing only**. This means:

1. You upload a video with `privacyStatus: "private"` and `publishAt: future_time`
2. The API returns `200 OK` with a video_id
3. YouTube accepts the upload, but silently restricts it to private viewing
4. At `publishAt` time, YouTube does NOT auto-publish; the video stays private forever
5. No error is returned; you only discover this when checking the channel

This is not an authorization error (which would be a 403). It's a silent restriction that only manifests at publish time.

## Solution: Upload a Private Canary

Before deploying public production uploads, verify your API project can publish to public. The test is simple:

1. Upload one test video in **private** mode
2. Schedule it for ~2 minutes in the future via `publishAt`
3. Wait for the scheduled time to pass
4. Check the video's actual `privacyStatus` on YouTube
5. If it auto-published to public, your project is clear
6. If it stayed private, your project needs audit completion

## Canary Upload Checklist

### 1. Create a Test Video

```bash
# Create a minimal test file (1 second, black frame)
ffmpeg -f lavfi -i color=black:s=1920x1080:d=1 -f lavfi -i anullsrc=r=44100 \
  -c:v libx264 -crf 28 -c:a aac -shortest /tmp/test_canary.mp4
```

### 2. Schedule the Canary

```bash
# UTC timestamp for ~2 minutes from now
PUBLISH_AT="$(date -d '+2 minutes' -u +'%Y-%m-%dT%H:%M:%SZ')"

python3 scripts/youtube_upload.py \
  --file /tmp/test_canary.mp4 \
  --title "API Project Audit Canary - $(date)" \
  --description "This is a test video for YouTube API project audit. Safe to delete." \
  --tags "test,audit" \
  --category 29 \
  --privacy private \
  --publish-at "$PUBLISH_AT"
```

The script will output:
```
PUBLISHED video_id=<VIDEO_ID> url=https://youtu.be/<VIDEO_ID> (scheduled for 2026-08-08T15:45:30Z)
```

### 3. Wait for Scheduled Time

Once the `publishAt` time has passed (wait a few minutes to be sure YouTube processed it):

```bash
python3 scripts/verify_upload.py \
  --video-id <VIDEO_ID> \
  --publish-at "2026-08-08T15:45:30Z"
```

Expected output if audit passes:
```
✓ All checks passed
Verified: True
```

If the video stayed private:
```
⚠️  1 issue(s):
  - Expected privacyStatus='private' but got 'private' — video is already public or misconfig
```

### 4. Interpret Results

**If public:** Your API project is audit-ready. Public uploads will work.

**If still private:** Your API project needs audit completion:
- Visit [Google Cloud Console](https://console.cloud.google.com/)
- Navigate to your YouTube API project
- Check **APIs & Services > OAuth consent screen** for:
  - App verification status (should be "verified" for production)
  - Brand verification (may be pending)
  - Sensitive scopes approval (if needed)
- Complete any required verification steps
- Delete the canary video and re-test with a fresh upload

## Post-Audit

Once the canary uploads and auto-publishes to public:

1. Delete the canary video from YouTube Studio
2. Record the test date and result in this file
3. Proceed with public production uploads

If the canary fails:
1. Do NOT attempt public uploads until audit is complete
2. Quarantine any uploads made during the "unknown state" period
3. Complete the GCP audit steps
4. Re-test with a fresh canary
5. Only then resume production

## Audit History

| Date | Result | Notes |
|------|--------|-------|
| [TBD] | [PENDING] | First audit before production launch |

---

See YOUTUBE_AUTOMATION_REPLICATION_GUIDE.md section 10.3 for full context.
