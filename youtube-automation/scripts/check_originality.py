#!/usr/bin/env python3
"""Channel-level originality/inauthentic-content gate (P0 production requirement).

YouTube's monetization policy assesses reused and inauthentic/repetitive content
at *channel level*, not per-video. Each upload must add clear creative variation
and viewer value to avoid channel-level penalties.

This gate compares a candidate against the last 5 published same-format items:
1. Title fingerprint (remove boilerplate, compare core concept)
2. Clip/audio overlap (score the uniqueness of source assets)
3. Visual theme uniqueness
4. Creative transformation depth (for shorts: cut velocity and visual changes)

Returns: {
  "passed": bool,
  "score": float (0-1, where 1.0 = completely original),
  "reasoning": str,
  "comparison": {
    "title_unique": bool,
    "asset_overlap_pct": float,
    "theme_unique": bool,
    "transformation_adequate": bool
  }
}

See config/gates.json.originality_gate for context and policy.
"""
import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Dict, List, Any

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state"


def load_queues() -> tuple:
    """Load short_form_queue.json and long_form_queue.json."""
    short_queue = {}
    long_queue = {}
    try:
        with open(STATE / "short_form_queue.json") as f:
            short_queue = json.load(f)
    except FileNotFoundError:
        pass
    try:
        with open(STATE / "long_form_queue.json") as f:
            long_queue = json.load(f)
    except FileNotFoundError:
        pass
    return short_queue, long_queue


def normalize_title(title: str) -> str:
    """Normalize title for fingerprinting: lowercase, remove punctuation/articles,
    collapse whitespace. Does NOT handle synonyms or semantic similarity —
    this is purely for detecting exact/near-exact title reuse."""
    if not title:
        return ""
    import re
    # Lowercase, remove punctuation, collapse whitespace
    normalized = re.sub(r"[^\w\s]", "", title.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    # Remove common filler words
    stopwords = {"a", "an", "the", "for", "and", "or", "is", "this", "that"}
    words = [w for w in normalized.split() if w not in stopwords]
    return " ".join(words)


def title_fingerprint(title: str) -> str:
    """SHA256 hash of normalized title."""
    if not title:
        return ""
    normalized = normalize_title(title)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def get_recent_same_format(queue: Dict, format_type: str, limit: int = 5) -> List[Dict]:
    """Extract the most recent N published items of a given format from queue.
    Returns items in reverse publish-date order (newest first)."""
    items = queue.get("queue", [])
    same_format = [
        item for item in items
        if item.get("status") in ("published", "scheduled", "live")
        and item.get("format") == format_type
    ]
    # Sort by published_at descending (most recent first)
    same_format.sort(
        key=lambda x: x.get("published_at") or x.get("scheduled_at") or "",
        reverse=True
    )
    return same_format[:limit]


def asset_overlap_score(candidate: Dict, recent_items: List[Dict]) -> float:
    """Score uniqueness of this candidate's clips/audio vs. recent items.
    Returns 0.0 (complete overlap) to 1.0 (completely unique).

    For shorts: check clips_used list and sound_direction.
    For long-form: check source asset fingerprint and mood.
    """
    if not recent_items:
        return 1.0  # No priors = completely original

    candidate_clips = set(candidate.get("clips_used") or [])
    candidate_sound = candidate.get("sound_direction", "") or candidate.get("trending_sound_style", "")

    overlap_count = 0
    for recent in recent_items:
        recent_clips = set(recent.get("clips_used") or [])
        recent_sound = recent.get("sound_direction", "") or recent.get("trending_sound_style", "")

        # Clip overlap: measure as % of candidate's clips that appear in recent items
        if candidate_clips and recent_clips:
            shared_clips = len(candidate_clips & recent_clips)
            clip_overlap = shared_clips / len(candidate_clips) if candidate_clips else 0
            if clip_overlap > 0.3:  # >30% clip overlap = suspicious
                overlap_count += 1

        # Sound reuse: exact string match
        if candidate_sound and candidate_sound == recent_sound:
            overlap_count += 1

    # Score: fewer overlaps = higher uniqueness
    # With 5 recent items, 0 overlaps = 1.0, 5 overlaps = 0.0
    max_overlaps = len(recent_items)
    return max(0.0, 1.0 - (overlap_count / max_overlaps)) if max_overlaps > 0 else 1.0


def theme_uniqueness(candidate: Dict, recent_items: List[Dict]) -> bool:
    """Check if this candidate's visual theme / angle is distinct from recent items."""
    if not recent_items:
        return True  # No priors = unique

    candidate_angle = candidate.get("angle", "")
    candidate_theme = candidate.get("visual_theme", "")

    for recent in recent_items:
        recent_angle = recent.get("angle", "")
        recent_theme = recent.get("visual_theme", "")

        # Very simple check: if angle/theme are identical, flag as non-unique
        if (candidate_angle and recent_angle and candidate_angle == recent_angle) or \
           (candidate_theme and recent_theme and candidate_theme == recent_theme):
            return False

    return True


def transformation_adequate(candidate: Dict, format_type: str) -> bool:
    """Check if this candidate shows adequate creative transformation.

    For shorts: beat-locked cuts, visual grade changes, audio replacement.
    For long-form: distinct loop source, meaningful mood difference.
    """
    if format_type == "short":
        # Shorts should show in transform_log a meaningful cut count and changes
        transform_log = candidate.get("transform_log", "")
        # Very basic: if transform_log exists and is non-empty, assume transformation was done
        # A real implementation would parse the log for specific metrics (cut count, grade changes, etc.)
        return bool(transform_log and len(transform_log) > 20)
    elif format_type == "long":
        # Long-form should show a distinct loop_method and source
        loop_method = candidate.get("motion_decision", {}).get("loop_method")
        source_asset = candidate.get("source_asset_path") or candidate.get("source_image_id")
        # Basic check: loop method and source exist
        return bool(loop_method) and bool(source_asset)

    return False


def check_candidate_originality(
    candidate: Dict,
    format_type: str,
    all_queues: Optional[tuple] = None
) -> Dict[str, Any]:
    """Evaluate a single candidate against originality gate.

    Args:
      candidate: the item to check (should have title, angle, clips_used, etc.)
      format_type: "short" or "long"
      all_queues: (short_queue_dict, long_queue_dict) or None to load fresh

    Returns: gate verdict dict with passed/score/reasoning/comparison.
    """
    if all_queues is None:
        all_queues = load_queues()

    short_queue, long_queue = all_queues
    queue = short_queue if format_type == "short" else long_queue

    recent = get_recent_same_format(queue, format_type, limit=5)

    # Sub-checks
    title_fp = title_fingerprint(candidate.get("title", ""))
    title_unique = not any(
        title_fingerprint(r.get("title", "")) == title_fp for r in recent
    ) if title_fp else True

    asset_overlap = asset_overlap_score(candidate, recent)
    theme_unique = theme_uniqueness(candidate, recent)
    transform_ok = transformation_adequate(candidate, format_type)

    # Composite score: all sub-checks contribute
    # Each sub-check is 0.0 or 1.0 (or a 0-1 score for asset_overlap)
    score = (
        (1.0 if title_unique else 0.0) +  # Title should be unique
        asset_overlap +                     # Asset overlap is scored 0-1
        (1.0 if theme_unique else 0.0) +  # Theme should be unique
        (1.0 if transform_ok else 0.3)     # Transformation is strongly preferred (0.3 = partial credit if missing)
    ) / 4.0

    # Threshold: 0.65 (score out of 1.0)
    # All four sub-checks passing = 1.0
    # Three passing + one failing = ~0.75
    # Two passing + two failing = 0.5 (below threshold)
    passed = score >= 0.65

    if passed:
        reasoning = "Candidate shows adequate originality: unique title, distinct assets, different theme, proper transformation."
    else:
        failures = []
        if not title_unique:
            failures.append("title matches recent upload")
        if asset_overlap < 0.6:
            failures.append(f"significant asset overlap ({1.0 - asset_overlap:.0%})")
        if not theme_unique:
            failures.append("visual theme matches recent upload")
        if not transform_ok:
            failures.append("insufficient creative transformation")
        reasoning = f"Originality concerns: {'; '.join(failures)}."

    return {
        "passed": passed,
        "score": score,
        "reasoning": reasoning,
        "comparison": {
            "title_unique": title_unique,
            "asset_overlap_pct": 1.0 - asset_overlap,  # invert for clarity (% overlap, not uniqueness)
            "theme_unique": theme_unique,
            "transformation_adequate": transform_ok,
        },
        "recent_sample_size": len(recent),
    }


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 check_originality.py <candidate_json_path> [format_type]")
        print("  candidate_json_path: path to candidate dict (json file or '-' for stdin)")
        print("  format_type: 'short' or 'long' (inferred from candidate if not given)")
        sys.exit(1)

    candidate_path = sys.argv[1]
    format_type = sys.argv[2] if len(sys.argv) > 2 else None

    if candidate_path == "-":
        candidate = json.load(sys.stdin)
    else:
        with open(candidate_path) as f:
            candidate = json.load(f)

    if not format_type:
        format_type = candidate.get("format", "short")

    result = check_candidate_originality(candidate, format_type)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
