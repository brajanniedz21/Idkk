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
