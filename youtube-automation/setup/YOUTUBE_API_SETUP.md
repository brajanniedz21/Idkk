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

### Known issue as of 2026-07-28: the scope doesn't actually work yet

After the steps above, `yt-analytics.readonly` shows up in `secrets/youtube_token.json`'s stored scope list, and single API calls worked right after re-authorizing — but refreshing the token with that scope fails with `invalid_scope`, meaning it stops working as soon as the original access token expires (roughly an hour). This is most likely because `yt-analytics.readonly` is one of Google's "sensitive" scopes, and something about the app's OAuth consent screen configuration for it wasn't fully accepted — just adding the scope string to the list (step 2 above) may not be enough on its own.

Things worth checking if you want to try fixing this:
- On the **OAuth consent screen**, under whatever section lists sensitive/restricted scopes, confirm `yt-analytics.readonly` actually shows as **saved** (not just entered) — Google sometimes requires re-saving the whole consent screen configuration after adding a sensitive scope.
- Some sensitive scopes prompt for extra app info (privacy policy URL, app icon) even in Testing mode — check if the console is flagging anything as incomplete.
- If it's still broken after checking those, it may need Google's own review process for sensitive scopes even for a Testing-mode app with test users — this isn't something to keep retrying blindly.

The pipeline itself handles this gracefully either way — `scripts/youtube_auth.py` keeps the base publishing scopes (`youtube.upload`/`youtube`/`youtube.readonly`) in a separate, isolated credential path from the analytics scope specifically so a broken analytics grant can never block uploads again (it briefly did, before this was split out) — see `load_credentials()` vs `load_analytics_credentials()` in that file.
