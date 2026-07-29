# YouTube Data API v3 setup for @makeitmanifest

This is the one part of the whole pipeline that only you can do — it requires your Google login. It's free (no billing needed) and takes about 10 minutes. Once done, Agent 4.1 and Agent 6 can publish autonomously with no further action from you.

Credentials from this process must **never** be committed to git. `youtube-automation/secrets/` is already git-ignored — put everything there.

## 1. Create a Google Cloud project
1. Go to https://console.cloud.google.com/ and log in with the Google account that owns @makeitmanifest (or an account with manage/upload permission on that channel).
2. Click the project dropdown (top left) → **New Project**.
3. Name it something like `makeitmanifest-automation`, no organization needed. Create it.

## 2. Enable the YouTube Data API v3
1. With the new project selected, go to **APIs & Services → Library**.
2. Search "YouTube Data API v3", open it, click **Enable**.

## 3. Configure the OAuth consent screen
1. Go to **APIs & Services → OAuth consent screen**.
2. User type: **External** (unless you have a Google Workspace org, in which case Internal also works).
3. Fill in app name (e.g. "Make It Manifest Automation"), your email as support/contact.
4. Scopes: add `https://www.googleapis.com/auth/youtube.upload` and `https://www.googleapis.com/auth/youtube` (readonly analytics scope `https://www.googleapis.com/auth/youtube.readonly` too, for the weekly analytics cycle).
5. Test users: add the Google account email that owns the channel (required while the app is in "Testing" publishing status — this is fine indefinitely for personal use, no need to submit for verification).

## 4. Create OAuth client credentials
1. Go to **APIs & Services → Credentials → Create Credentials → OAuth client ID**.
2. Application type: **Desktop app**.
3. Name it, create it.
4. Download the JSON — save it as `youtube-automation/secrets/client_secret.json` in this repo (this path is git-ignored).

## 5. Run the one-time authorization to get a refresh token
This step opens a browser consent screen and only needs to run once — after this, the refresh token lets the automation mint new access tokens indefinitely without you clicking anything again.

Run this from a machine where you can open a browser (this can be your own computer — it doesn't need to be this cloud session):

```bash
pip install google-auth-oauthlib google-api-python-client
python3 - <<'EOF'
from google_auth_oauthlib.flow import InstalledAppFlow
import json

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]

flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
creds = flow.run_local_server(port=0)

with open("youtube_token.json", "w") as f:
    f.write(creds.to_json())

print("Saved youtube_token.json — copy this into youtube-automation/secrets/")
EOF
```

1. This opens your browser, asks you to log in as the channel owner and grant the requested scopes (you'll see a Google "unverified app" warning since the app is in Testing mode with you as a test user — click **Advanced → Go to (app name)** to proceed; this is expected and safe since it's your own app).
2. It saves `youtube_token.json` containing a refresh token.
3. Copy that file into `youtube-automation/secrets/youtube_token.json` in this repo (git-ignored — never commit it).

## 6. Confirm it's in place
Once both files exist:
- `youtube-automation/secrets/client_secret.json`
- `youtube-automation/secrets/youtube_token.json`

tell me, and I'll wire `scripts/youtube_auth.py` / `scripts/youtube_upload.py` to use them and unblock Agent 4.1 and Agent 6.

## Quota notes
The YouTube Data API's free daily quota (10,000 units/day) comfortably covers this channel's schedule: an upload costs ~1,600 units, so even 4 uploads/day (3 shorts + 1 long-form) is ~6,400 units — well within the free daily limit. No billing account is required for this quota tier.

## Adding YouTube Analytics access (owner requested, 2026-07-28)

The setup above only grants basic Data API scopes — enough to upload and to read public stats (views/likes/comments via `videos.list`), but **not** enough for the real YouTube Analytics API (watch time, audience retention curves, click-through rate/impressions, traffic sources, subscriber/demographic data). That needs one additional scope and a fresh consent, since scopes are locked in at the moment you approve them — the existing refresh token can't silently gain a new permission.

This is a ~5 minute repeat of steps 3-5 above, not a full redo:

1. **Enable the extra API.** In the same Google Cloud project (`makeitmanifest-automation` or whatever you named it) → **APIs & Services → Library** → search "**YouTube Analytics API**" → **Enable**. (Distinct from "YouTube Data API v3", which is already enabled.)
2. **Add the scope to the consent screen.** **APIs & Services → OAuth consent screen → Data Access** (or **Scopes**, depending on the current console layout) → **Add or Remove Scopes** → search/add `https://www.googleapis.com/auth/yt-analytics.readonly` → save.
3. **Re-run the authorization flow** — same as step 5 above, but with the extra scope. Using the *same* `client_secret.json` you already downloaded (no need to create a new OAuth client):

   ```bash
   python3 - <<'EOF'
   from google_auth_oauthlib.flow import InstalledAppFlow

   SCOPES = [
       "https://www.googleapis.com/auth/youtube.upload",
       "https://www.googleapis.com/auth/youtube",
       "https://www.googleapis.com/auth/youtube.readonly",
       "https://www.googleapis.com/auth/yt-analytics.readonly",
   ]

   flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
   creds = flow.run_local_server(port=0)

   with open("youtube_token.json", "w") as f:
       f.write(creds.to_json())

   print("Saved youtube_token.json — copy this into youtube-automation/secrets/, overwriting the old one")
   EOF
   ```

   Run this from a machine with a browser, in the same directory as your `client_secret.json`. You'll see the same "unverified app" warning as before — same click-through as last time. This time the consent screen will list an extra permission ("View YouTube Analytics reports") — approve it too.
4. **Overwrite** `youtube-automation/secrets/youtube_token.json` with the new file (same filename, same location — it replaces the old one, which only had the narrower scopes).
5. Tell me once it's replaced and I'll verify the new scope is live and start actually pulling analytics data (views alone were already working; this unlocks retention/traffic-source data for the daily analytics cycle in `agents/0_orchestrator.md` — note CTR/impressions specifically are NOT available through this API at all, confirmed via a live 400 error, regardless of scopes; that one's YouTube Studio-only).

### Resolved 2026-07-28: the scope initially didn't work, here's what actually fixed it

For most of one day, `yt-analytics.readonly` showed up correctly in `secrets/youtube_token.json`'s stored scope list, and single API calls worked right after re-authorizing — but refreshing the token with that scope failed with `invalid_scope`, meaning it stopped working as soon as the original access token expired (roughly an hour). The OAuth consent screen's **Data Access** page confirmed the scope *was* properly configured (listed under non-sensitive scopes, nothing flagged missing), which ruled out a Cloud Console configuration problem. `prompt=consent` on the re-auth script didn't fix it either.

**The actual cause:** Google was reusing the original refresh token (tied only to the base 3 scopes) across every re-auth attempt instead of issuing a genuinely new one for the expanded scope set — this happens when an app already has an existing offline grant for your account, and re-approving doesn't always replace it, even when you approve new scopes in the consent screen.

**The actual fix:**
1. Go to **myaccount.google.com/permissions** (Google Account → Security → "Third-party apps & services")
2. Find the app and click **Remove Access** — this deletes the old grant entirely.
3. Re-run the token script with `prompt="consent", access_type="offline"` passed to `run_local_server(...)`. With no prior grant left to reuse, Google issues a genuinely new refresh token this time.
4. **Verify with an actual forced refresh call, not just one live API call right after auth** — a fresh access token can work immediately even when the underlying refresh token is broken, which is exactly what made this look intermittently "fixed" several times before it actually was.

If this ever regresses after a future re-authorization, this is the fix to reach for again — not re-checking the consent screen configuration, which was correct the whole time.

## Adding comment-posting access for the Shorts→long-form funnel (owner requested, 2026-07-30)

The Shorts→long-form funnel (every Short gets a pinned comment pointing to the long-form catalog) needs a scope the current token doesn't have: `https://www.googleapis.com/auth/youtube.force-ssl`. Without it, `scripts/post_pinned_comment.py` just prints "SKIPPED" and does nothing — it never blocks or fails a video publish, but comments won't actually post until this is added.

This is the same ~5 minute repeat of the re-auth flow as the analytics scope above, and the same lesson applies: revoke access first, don't just re-run with the scope added, or Google may silently reuse the old refresh token again.

1. **Add the scope to the consent screen.** APIs & Services → OAuth consent screen → Data Access (or Scopes) → Add or Remove Scopes → search/add `https://www.googleapis.com/auth/youtube.force-ssl` → save.
2. **Revoke the app's existing access first** at myaccount.google.com/permissions (Security → Third-party apps & services → find the app → Remove Access) — this is not optional; skipping it is exactly what caused the analytics scope to silently fail for a day (see above).
3. **Re-run the token script** with all four scopes now (the three base ones + analytics + this one):
   ```python
   from google_auth_oauthlib.flow import InstalledAppFlow

   SCOPES = [
       "https://www.googleapis.com/auth/youtube.upload",
       "https://www.googleapis.com/auth/youtube",
       "https://www.googleapis.com/auth/youtube.readonly",
       "https://www.googleapis.com/auth/yt-analytics.readonly",
       "https://www.googleapis.com/auth/youtube.force-ssl",
   ]

   flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
   creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

   with open("youtube_token.json", "w") as f:
       f.write(creds.to_json())

   print("Saved youtube_token.json — copy this into youtube-automation/secrets/, overwriting the old one")
   ```
4. **Overwrite** `youtube-automation/secrets/youtube_token.json` with the new file.
5. Tell me once it's replaced and I'll verify with a real forced-refresh test (not just one live call) before trusting it, same discipline as the analytics fix.

Until this is done, pinned comments simply won't post — everything else (uploads, thumbnails, scheduling) is unaffected, since this scope is isolated in its own credential loader (`load_comment_credentials()`) and never touches the base publish scopes.

Note on what "pinning" actually means here: the YouTube Data API v3 has no dedicated "pin comment" endpoint. `post_pinned_comment.py` posts the comment as the channel owner; YouTube typically shows the channel owner's own comment with a "Pinned by creator" affordance automatically in some contexts, but if it doesn't auto-pin, pinning it for real requires one manual click in YouTube Studio. This is disclosed plainly in the script's own output rather than silently claiming a pin that didn't happen.
