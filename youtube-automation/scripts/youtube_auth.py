#!/usr/bin/env python3
"""Load YouTube API credentials from youtube-automation/secrets/, refreshing the
access token from the stored refresh token as needed. Never prompts a browser
flow here — that one-time step is documented in setup/YOUTUBE_API_SETUP.md and
must already have produced the credential files before this script is used.

Production design (as of 2026-08-08): three separate, isolated credential files
(youtube_upload_token.json, youtube_analytics_token.json, youtube_comment_token.json)
so a failing scope never breaks the others (see P0 item 5 of YOUTUBE_AUTOMATION_
REPLICATION_GUIDE.md). Falls back to legacy youtube_token.json for backward
compatibility during migration.
"""
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

REPO_ROOT = Path(__file__).resolve().parent.parent
SECRETS_DIR = REPO_ROOT / "secrets"

# Production paths (separate token files)
UPLOAD_TOKEN_PATH = SECRETS_DIR / "youtube_upload_token.json"
ANALYTICS_TOKEN_PATH = SECRETS_DIR / "youtube_analytics_token.json"
COMMENT_TOKEN_PATH = SECRETS_DIR / "youtube_comment_token.json"

# Legacy fallback (migration path)
LEGACY_TOKEN_PATH = SECRETS_DIR / "youtube_token.json"

# The scopes that are confirmed working end-to-end (including token
# refresh) as of 2026-07-28 — publishing depends on these, so this list
# must never include a scope that isn't verified to refresh cleanly.
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.readonly",
]

# yt-analytics.readonly — isolated scope set (separate token, never merged
# into SCOPES) because it's a Google "sensitive" scope. Broken analytics
# refresh must never break publishing. This token file is separate and
# optional (load_analytics_credentials returns None if unavailable).
ANALYTICS_SCOPES = ["https://www.googleapis.com/auth/yt-analytics.readonly"]

# Comment-posting needs youtube.force-ssl specifically — isolated and optional
# (load_comment_credentials returns None if unavailable). Never merged into SCOPES.
COMMENT_SCOPES = ["https://www.googleapis.com/auth/youtube.force-ssl"]


def _load_or_fallback(primary_path, scopes, name):
    """Load from primary path, fall back to legacy youtube_token.json if needed.
    Returns (Credentials, used_path_str) or (None, reason_str) on failure."""
    if primary_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(primary_path), scopes)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            return creds, str(primary_path)
        except Exception as e:
            return None, f"{name} credentials from {primary_path.name} failed: {e}"

    # Fallback to legacy youtube_token.json
    if LEGACY_TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(LEGACY_TOKEN_PATH), scopes)
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
            print(f"[Migration] Loaded {name} from legacy {LEGACY_TOKEN_PATH.name}", file=sys.stderr)
            return creds, str(LEGACY_TOKEN_PATH)
        except Exception as e:
            return None, f"{name} credentials from legacy {LEGACY_TOKEN_PATH.name} failed: {e}"

    return None, f"Neither {primary_path.name} nor legacy {LEGACY_TOKEN_PATH.name} found"


def load_credentials() -> Credentials:
    """Load upload credentials (youtube.upload + youtube + youtube.readonly scopes).
    Uses youtube_upload_token.json if available, falls back to legacy youtube_token.json.
    Raises FileNotFoundError if neither exists."""
    creds, path_or_reason = _load_or_fallback(UPLOAD_TOKEN_PATH, SCOPES, "Upload")
    if creds:
        return creds
    raise FileNotFoundError(
        f"{path_or_reason}. Follow setup/YOUTUBE_API_SETUP.md to "
        "generate credential files before publishing can run."
    )


def load_analytics_credentials():
    """Load analytics credentials (yt-analytics.readonly scope).
    Uses youtube_analytics_token.json if available, falls back to legacy youtube_token.json.
    Returns None if credentials are unavailable or fail to refresh (non-fatal — analytics
    is optional). Callers must handle None as "analytics not available right now"."""
    if not ANALYTICS_TOKEN_PATH.exists() and not LEGACY_TOKEN_PATH.exists():
        return None
    try:
        creds, _path = _load_or_fallback(ANALYTICS_TOKEN_PATH, ANALYTICS_SCOPES, "Analytics")
        if creds:
            return creds
        # Fallback failed or returned None; log but don't crash
        print(f"Analytics credentials unavailable (non-fatal)", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Analytics credentials error (non-fatal): {e}", file=sys.stderr)
        return None


def load_comment_credentials():
    """Load comment-posting credentials (youtube.force-ssl scope).
    Uses youtube_comment_token.json if available, falls back to legacy youtube_token.json.
    Returns None if credentials are unavailable or fail to refresh (non-fatal — comments
    are optional). Callers (e.g. post_pinned_comment.py) must handle None as
    'comment posting not available right now' and skip gracefully."""
    if not COMMENT_TOKEN_PATH.exists() and not LEGACY_TOKEN_PATH.exists():
        return None
    try:
        creds, _path = _load_or_fallback(COMMENT_TOKEN_PATH, COMMENT_SCOPES, "Comment")
        if creds:
            return creds
        # Fallback failed or returned None; log but don't crash
        print(f"Comment-posting credentials unavailable (non-fatal)", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Comment-posting credentials error (non-fatal): {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    print("Checking YouTube API credentials (production setup with separate token files):")
    print()

    # Upload (required)
    try:
        c = load_credentials()
        print(f"✓ Upload credentials: OK (valid={c.valid})")
    except Exception as e:
        print(f"✗ Upload credentials: FAILED - {e}")
        sys.exit(1)

    # Analytics (optional)
    ac = load_analytics_credentials()
    if ac and ac.valid:
        print(f"✓ Analytics credentials: OK (valid={ac.valid})")
    else:
        print(f"⊘ Analytics credentials: NOT available (non-fatal)")

    # Comments (optional)
    cc = load_comment_credentials()
    if cc and cc.valid:
        print(f"✓ Comment-posting credentials: OK (valid={cc.valid})")
    else:
        print(f"⊘ Comment-posting credentials: NOT available (non-fatal)")

    print()
    print("Separate credential files enable fault isolation:")
    print(f"  - Upload (required): {UPLOAD_TOKEN_PATH} (or legacy {LEGACY_TOKEN_PATH.name})")
    print(f"  - Analytics (optional): {ANALYTICS_TOKEN_PATH} (or legacy {LEGACY_TOKEN_PATH.name})")
    print(f"  - Comments (optional): {COMMENT_TOKEN_PATH} (or legacy {LEGACY_TOKEN_PATH.name})")
    print()
    print("See setup/YOUTUBE_API_SETUP.md to migrate from legacy to separate token files.")
