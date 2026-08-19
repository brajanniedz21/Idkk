# OAuth Production Status Migration

**Status:** P0 production requirement  
**Current state:** External OAuth app in Testing (limited lifetime tokens)  
**Target state:** Production OAuth app with appropriate verification  
**Timeline:** Before first unattended production run

## Problem

External OAuth applications in **Testing** status have limitations:

- Refresh tokens expire after **7 days** (not 6 months like production tokens)
- Require manual browser re-authorization every week
- Cannot run unattended for more than a week
- Will silently fail with `invalid_grant` when refresh token expires

For production (unattended daily runs), you need:

- Production OAuth publishing status (or appropriate tier)
- Longer-lived refresh tokens (minimum ~1 month, ideally indefinite)
- No manual re-consent required during normal operation

## Migration Steps

### Step 1: Determine Your Required Status

Choose based on your use case:

| Status | Lifetime | Verification | Use Case |
|--------|----------|--------------|----------|
| **Testing** (current) | 7 days | None | Development/testing only |
| **Production** (recommended) | ~6 months | App name, logo, privacy policy | Unattended automation |

For @makeitmanifest, Production status is appropriate since this is unattended automation publishing to a real channel.

### Step 2: Complete Brand Verification (if needed)

If moving to Production, Google may require:

1. **Brand verification**: verify you own the domain/organization
2. **Sensitive scopes approval**: `youtube.upload` is considered sensitive
3. **Privacy policy**: must have one if your app collects user data (ours doesn't)

Visit [Google Cloud Console > APIs & Services > OAuth consent screen](https://console.cloud.google.com/apis/credentials/consent):

- [ ] App name is accurate
- [ ] App logo is uploaded (if required)
- [ ] Privacy policy URL is valid (if required)
- [ ] Authorized domain includes your domain (not needed for local/CLI apps)

### Step 3: Change OAuth Status

In the same OAuth consent screen:

- [ ] Change **Publishing status** from "Testing" to "Production"
- [ ] Complete any additional verification Google prompts for
- [ ] Wait for approval (usually instant, sometimes 1-3 days)

### Step 4: Force Token Refresh

Once Production status is active, you must **revoke and re-authorize** to get new long-lived tokens:

```bash
# Step 1: Revoke the old (Testing-status) token
rm secrets/youtube_token.json
rm secrets/youtube_upload_token.json
rm secrets/youtube_analytics_token.json
rm secrets/youtube_comment_token.json

# Step 2: Run the setup to trigger a browser re-auth
python3 setup/YOUTUBE_API_SETUP.md
# (Or manually run the auth flow in that script)

# This will save NEW tokens with the PRODUCTION status
# Refresh tokens from Production status will last ~6 months
```

### Step 5: Verify Long-Lived Tokens

```bash
# Test that the new tokens have a long lifetime
python3 scripts/youtube_auth.py

# Expected output:
# ✓ Upload credentials: OK (valid=True)
# ✓ Analytics credentials: OK (valid=True)
# ✓ Comment-posting credentials: OK (valid=True)
```

### Step 6: Monitor Token Expiry

Track refresh token expiry:

```bash
# Check when the current refresh token was issued
python3 -c "import json; print(json.load(open('secrets/youtube_upload_token.json')))['token_expiry']"
```

Long-lived tokens (6 months) should show an expiry date ~6 months in the future.

### Step 7: Set up Periodic Re-authorization (Optional but Recommended)

Even with long-lived tokens, re-authorizing every 6 months is a good safety practice:

1. Calendar reminder: "Re-authorize YouTube API tokens" (6-month intervals)
2. When reminder fires: run `setup/YOUTUBE_API_SETUP.md` to get fresh tokens
3. This prevents any edge cases where tokens become invalid

## Rollback Plan

If something goes wrong:

1. Revert to Testing status in OAuth consent screen (takes effect immediately)
2. Revoke all tokens
3. Re-run the auth flow to get Testing tokens (7-day lifetime)
4. Test thoroughly before attempting production migration again

## Verification Checklist

Before declaring this step complete:

- [ ] OAuth app status changed to Production (visible in Cloud Console)
- [ ] New tokens obtained via fresh auth flow
- [ ] `python3 scripts/youtube_auth.py` passes for all three credential types
- [ ] Test upload scheduled for future (to confirm publishAt works)
- [ ] Re-run API_PROJECT_AUDIT canary upload (to verify overall project status)
- [ ] Document completion date in this file

## Completion Status

| Date | Status | Notes |
|------|--------|-------|
| [TBD] | PENDING | Complete brand verification + status migration + token refresh |

---

See YOUTUBE_AUTOMATION_REPLICATION_GUIDE.md section 11.2 for full context.
See setup/YOUTUBE_API_SETUP.md for the full auth flow.
