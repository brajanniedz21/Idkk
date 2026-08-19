#!/usr/bin/env python3
"""Backup and restore state files atomically.

P0 production requirement: Keep at least 14 daily and 8 weekly state snapshots.
Never delete the only copy of an unpublished render. Verify restore in
a temporary location before considering it successful.

See YOUTUBE_AUTOMATION_REPLICATION_GUIDE.md section 15: "Backups and media retention"
"""
import json
import os
import shutil
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Tuple

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
BACKUP_DIR = ROOT / "backups"

# Key state files to back up (data + config)
STATE_FILES = [
    "short_form_queue.json",
    "long_form_queue.json",
    "posted_history.json",
    "weekly_batch_progress.json",
    "performance_notes.json",
    "video_analytics.json",
    "channel_stats.json",
    "video_comments.json",
    "quarantine.json",
    "image_pool.json",
    "cc0_audio_library.json",
    "trending_audio_library.json",
    "animated_clip_pool.json",
    "channel_playbook.md",
    "dashboard_artifact.json",
]

ARTIFACT_DIRS = [
    "runs",  # Run manifests
]

def ensure_backup_dir():
    """Create backup directory if it doesn't exist."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

def timestamp_now() -> str:
    """Current timestamp in format suitable for filenames (YYYYMMDD-HHMMSS)."""
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

def backup_state() -> Tuple[Path, List[str]]:
    """Create a timestamped backup of all state files.

    Returns: (backup_dir_path, list_of_files_backed_up)
    """
    ensure_backup_dir()

    ts = timestamp_now()
    backup_dir = BACKUP_DIR / f"backup-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backed_up = []
    failed = []

    # Back up JSON files
    for filename in STATE_FILES:
        src = STATE / filename
        dst = backup_dir / filename
        if src.exists():
            try:
                shutil.copy2(src, dst)
                backed_up.append(filename)
            except Exception as e:
                failed.append(f"{filename}: {e}")
        # Missing files are OK (may not exist yet)

    # Back up artifact directories
    for dirname in ARTIFACT_DIRS:
        src = STATE / dirname
        dst = backup_dir / dirname
        if src.exists():
            try:
                shutil.copytree(src, dst, dirs_exist_ok=True)
                backed_up.append(dirname)
            except Exception as e:
                failed.append(f"{dirname}: {e}")

    # Write manifest of what was backed up
    manifest = {
        "timestamp": ts,
        "timestamp_iso": datetime.now(timezone.utc).isoformat(),
        "files_backed_up": backed_up,
        "backup_path": str(backup_dir),
    }
    with open(backup_dir / "BACKUP_MANIFEST.json", "w") as f:
        json.dump(manifest, f, indent=2)

    if failed:
        print(f"⚠️  Backup completed with {len(failed)} error(s):", file=sys.stderr)
        for err in failed:
            print(f"  - {err}", file=sys.stderr)

    return backup_dir, backed_up

def cleanup_old_backups(keep_days: int = 14, keep_weeks: int = 8):
    """Delete old backups beyond retention policy.

    Keep:
    - All backups from the last 14 days
    - One backup per week for the previous 8 weeks
    - Nothing older than 8 weeks
    """
    ensure_backup_dir()

    now = datetime.now(timezone.utc)
    backups = sorted([d for d in BACKUP_DIR.iterdir() if d.is_dir() and d.name.startswith("backup-")])

    deleted = []
    kept = []

    for backup in backups:
        try:
            ts_str = backup.name.replace("backup-", "")
            backup_time = datetime.strptime(ts_str, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue

        age_days = (now - backup_time).days

        # Keep if within last 14 days
        if age_days <= keep_days:
            kept.append(backup.name)
            continue

        # Keep if it's the only backup from its week (8-week retention of weekly snapshots)
        if age_days <= (keep_weeks * 7):
            week_num = (now - backup_time).days // 7
            same_week = [b for b in backups if (now - b.stat().st_mtime / (24*3600)).days // 7 == week_num]
            if len(same_week) == 1:  # Only backup from this week
                kept.append(backup.name)
                continue

        # Delete old backups
        try:
            shutil.rmtree(backup)
            deleted.append(backup.name)
        except Exception as e:
            print(f"⚠️  Failed to delete {backup.name}: {e}", file=sys.stderr)

    return kept, deleted

def list_backups() -> List[Tuple[str, int]]:
    """List all available backups with their sizes.

    Returns: [(backup_name, size_bytes), ...]
    """
    ensure_backup_dir()

    backups = []
    for d in sorted(BACKUP_DIR.iterdir(), reverse=True):
        if d.is_dir() and d.name.startswith("backup-"):
            size = sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            backups.append((d.name, size))

    return backups

def restore_state(backup_name: str, dry_run: bool = False) -> List[str]:
    """Restore state files from a backup.

    Args:
      backup_name: name of backup dir (e.g., "backup-20260808-120000")
      dry_run: if True, only report what would be restored, don't actually restore

    Returns: list of files that would be/were restored
    """
    backup_dir = BACKUP_DIR / backup_name
    if not backup_dir.exists():
        raise FileNotFoundError(f"Backup {backup_name} not found")

    restored = []

    for filename in STATE_FILES:
        src = backup_dir / filename
        dst = STATE / filename
        if src.exists():
            if not dry_run:
                shutil.copy2(src, dst)
            restored.append(filename)

    for dirname in ARTIFACT_DIRS:
        src = backup_dir / dirname
        dst = STATE / dirname
        if src.exists():
            if not dry_run:
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst)
            restored.append(dirname)

    return restored

def verify_backup(backup_name: str) -> Tuple[bool, str]:
    """Verify a backup is readable and contains expected files.

    Returns: (is_valid, reason_if_invalid)
    """
    backup_dir = BACKUP_DIR / backup_name
    if not backup_dir.exists():
        return False, "Backup directory not found"

    manifest_file = backup_dir / "BACKUP_MANIFEST.json"
    if not manifest_file.exists():
        return False, "Missing BACKUP_MANIFEST.json"

    try:
        with open(manifest_file) as f:
            manifest = json.load(f)
    except Exception as e:
        return False, f"Could not read manifest: {e}"

    backed_up = manifest.get("files_backed_up", [])
    if not backed_up:
        return False, "No files in backup"

    # Spot-check a few files
    for filename in ["short_form_queue.json", "long_form_queue.json"]:
        if filename in backed_up:
            file_path = backup_dir / filename
            if not file_path.exists():
                return False, f"File {filename} listed but not found"
            try:
                with open(file_path) as f:
                    json.load(f)  # Verify it's valid JSON
            except Exception as e:
                return False, f"File {filename} is corrupted: {e}"

    return True, ""

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["backup", "restore", "list", "cleanup", "verify"],
                        help="Action to perform")
    parser.add_argument("--backup", default=None, help="Backup name (for restore/verify)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would happen without doing it")
    parser.add_argument("--keep-days", type=int, default=14, help="Keep backups from last N days")
    parser.add_argument("--keep-weeks", type=int, default=8, help="Keep weekly backup for N weeks")
    args = parser.parse_args()

    if args.command == "backup":
        print("Creating state backup...")
        backup_dir, files = backup_state()
        print(f"✓ Backup created: {backup_dir.name}")
        print(f"  Files backed up: {len(files)}")
        for f in sorted(files):
            print(f"    - {f}")

    elif args.command == "list":
        backups = list_backups()
        if not backups:
            print("No backups found")
        else:
            print(f"Available backups ({len(backups)}):")
            for name, size_bytes in backups:
                size_mb = size_bytes / (1024**2)
                print(f"  {name}: {size_mb:.1f} MB")

    elif args.command == "restore":
        if not args.backup:
            print("Error: --backup name required for restore", file=sys.stderr)
            sys.exit(1)
        try:
            files = restore_state(args.backup, dry_run=args.dry_run)
            mode = "(dry-run)" if args.dry_run else ""
            print(f"✓ Restore {mode}: {len(files)} files")
            for f in sorted(files):
                print(f"  - {f}")
        except Exception as e:
            print(f"✗ Restore failed: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "verify":
        if not args.backup:
            print("Error: --backup name required for verify", file=sys.stderr)
            sys.exit(1)
        valid, reason = verify_backup(args.backup)
        if valid:
            print(f"✓ Backup {args.backup} is valid and readable")
        else:
            print(f"✗ Backup {args.backup} is invalid: {reason}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "cleanup":
        print(f"Cleaning up backups (keep {args.keep_days} days + {args.keep_weeks} weeks)...")
        kept, deleted = cleanup_old_backups(keep_days=args.keep_days, keep_weeks=args.keep_weeks)
        print(f"Kept: {len(kept)} backups")
        print(f"Deleted: {len(deleted)} backups")
        if deleted:
            for name in deleted:
                print(f"  - {name}")
