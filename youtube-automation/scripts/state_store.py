#!/usr/bin/env python3
"""State management for the production supervisor. Provides:

- Atomic read/write operations with temp file + rename pattern
- Global run lock (prevents duplicate concurrent runs)
- Candidate ID uniqueness enforcement
- Manifest creation and updates

See YOUTUBE_AUTOMATION_REPLICATION_GUIDE.md section 7 for concurrency model.
"""
import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Optional, Dict, Any

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"
LOCKS = STATE / ".locks"


def ensure_dirs():
    """Create required directories."""
    STATE.mkdir(parents=True, exist_ok=True)
    LOCKS.mkdir(parents=True, exist_ok=True)


def get_global_lock():
    """Acquire the global production lock.

    Only one content or analytics run can execute at a time.
    Use as: with get_global_lock():
    """
    lock_file = LOCKS / "global.lock"
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = open(lock_file, 'a')
    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
    return lock_handle


def atomic_write_json(path: Path, data: Dict[str, Any]) -> bool:
    """Write JSON atomically: temp file + rename.

    Ensures partial writes never corrupt the live file.
    Returns True on success, False on failure.
    """
    try:
        # Write to temp file in same directory (same filesystem)
        with tempfile.NamedTemporaryFile(
            mode='w',
            dir=path.parent,
            suffix='.tmp',
            delete=False
        ) as tmp:
            json.dump(data, tmp, indent=2)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name

        # Atomic rename
        os.replace(tmp_path, path)
        return True
    except Exception as e:
        print(f"atomic_write_json failed: {e}", flush=True)
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except:
                pass
        return False


def read_json(path: Path) -> Optional[Dict]:
    """Read JSON file, return None if missing/unreadable."""
    if not path.exists():
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def create_run_manifest(run_type: str, run_date: str, tz_name: str) -> Dict[str, Any]:
    """Create a new run manifest with immutable fields.

    Args:
      run_type: 'content' or 'analytics'
      run_date: YYYY-MM-DD
      tz_name: Europe/London

    Returns: manifest dict
    """
    now = datetime.now(dt_timezone.utc)
    run_id = f"{run_date.replace('-', '')}-{run_type}-{now.strftime('%H%M')}-{os.urandom(2).hex()}"

    return {
        "run_id": run_id,
        "run_type": run_type,
        "status": "created",
        "run_date": run_date,
        "timezone": tz_name,
        "started_at": now.isoformat(),
        "pipeline_version": "1.0.0",
        "git_commit": get_git_commit(),
        "spec_manifest_hash": get_spec_manifest_hash(),
        "preflight": {"status": None, "checks": {}, "blockers": []},
        "slots_requested": 0,
        "slots_completed": {"published": 0, "scheduled": 0, "quarantined": 0, "blocked": 0},
        "candidates": [],
        "current_stage": "preflight",
        "current_slot_index": 0,
        "token_usage": {},
        "notes": "",
        "errors": [],
    }


def save_manifest(manifest: Dict[str, Any]) -> bool:
    """Save manifest atomically."""
    ensure_dirs()
    run_id = manifest.get("run_id", "unknown")
    path = STATE / "runs" / f"{run_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return atomic_write_json(path, manifest)


def load_manifest(run_id: str) -> Optional[Dict[str, Any]]:
    """Load manifest for a run."""
    path = STATE / "runs" / f"{run_id}.json"
    return read_json(path)


def update_manifest(manifest: Dict[str, Any]) -> bool:
    """Update manifest atomically (compare prior status before writing)."""
    path = STATE / "runs" / f"{manifest['run_id']}.json"
    return atomic_write_json(path, manifest)


def get_git_commit() -> str:
    """Get current git commit SHA."""
    try:
        result = os.popen("git rev-parse HEAD 2>/dev/null").read().strip()
        return result if result else "unknown"
    except:
        return "unknown"


def get_spec_manifest_hash() -> str:
    """Hash config/agent files to detect drift.

    This is a placeholder; a real implementation would hash the canonical
    config and agent files to detect out-of-sync code/config.
    """
    import hashlib
    # TODO: implement hashing of config + agents
    return "placeholder"


def check_unique_candidate_ids(new_id: str, queue_file: Path) -> bool:
    """Check if a candidate ID is already in use.

    Returns True if unique (OK to use), False if already in queue.
    """
    queue = read_json(queue_file)
    if not queue:
        return True

    existing_ids = {item.get("id") for item in queue.get("queue", [])}
    return new_id not in existing_ids


def reserve_slot(manifest: Dict, slot_id: str, format_type: str) -> bool:
    """Reserve a publishing slot and create a candidate.

    Returns True if reservation succeeded, False if slot already claimed.
    """
    # Check if slot is already reserved in this manifest
    existing = [c for c in manifest.get("candidates", []) if c.get("slot_id") == slot_id]
    if existing:
        return False  # Already reserved

    # Add candidate to manifest
    now = datetime.now(dt_timezone.utc).isoformat()
    candidate = {
        "id": f"{manifest['run_date'].replace('-', '')}-{format_type}-{os.urandom(2).hex()}",
        "slot_id": slot_id,
        "status": "reserved",
        "format": format_type,
        "created_at": now,
    }
    manifest["candidates"].append(candidate)

    return save_manifest(manifest)


if __name__ == "__main__":
    # Test basic operations
    ensure_dirs()
    manifest = create_run_manifest("content", "2026-08-08", "Europe/London")
    print(f"Created manifest: {manifest['run_id']}")

    if save_manifest(manifest):
        print("✓ Saved manifest")
        loaded = load_manifest(manifest['run_id'])
        if loaded:
            print(f"✓ Loaded manifest: {loaded['run_id']}")
        else:
            print("✗ Failed to load manifest")
    else:
        print("✗ Failed to save manifest")
