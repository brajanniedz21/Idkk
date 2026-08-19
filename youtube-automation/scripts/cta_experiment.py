#!/usr/bin/env python3
"""Controlled CTA experimentation for YouTube Shorts descriptions (owner
direction, 2026-08-01). Extends the permanent Shorts CTA added earlier
(scripts/youtube_upload.py's original SHORTS_CTA/append_shorts_cta) into a
proper A/B/C/D experiment rather than one hard-coded string.

Scope, unchanged from the original CTA requirement: Shorts descriptions
only. Never titles, hashtags, thumbnails, captions, pinned comments, file
names, or long-form. scripts/youtube_upload.py still only touches the
description, and only when --short is passed.

CTA_LUXURY_EXPERIMENT is the one active experiment as of 2026-08-01 — see
its entry in state/performance_notes.json's experiment_ledger. New variants
are only ever added through a documented experiment decision, never
generated ad hoc here.
"""
import hashlib

CTA_LUXURY_EXPERIMENT_ID = "cta-luxury-001"

# Every value here must be usable as-is: exact punctuation/capitalization
# preserved, every variant contains the required "Luxury" keyword. The
# control text is unchanged from the original SHORTS_CTA constant
# (scripts/youtube_upload.py) — every Short published before this
# experiment existed already carries this exact string, so keeping it byte-
# identical as the control is what makes a pre-experiment/post-experiment
# comparison meaningful at all.
CTA_VARIANTS = {
    "cta_luxury_control": 'Manifest it. Comment "Luxury" below.',
    "cta_luxury_future": 'Comment "Luxury" if this is your future.',
    "cta_luxury_claim": 'Type "Luxury" to claim it.',
    "cta_luxury_begin": 'Your future starts here. Comment "Luxury".',
}

DEFAULT_VARIANT_ID = "cta_luxury_control"
_VARIANT_ORDER = list(CTA_VARIANTS)  # stable iteration order for block rotation


def assign_variant_by_rotation(sequence_index, variant_ids=None):
    """Balanced block rotation: the Nth Short assigned under this experiment
    gets variant_ids[N % len(variant_ids)]. Exactly balanced over any run
    length that's a multiple of len(variant_ids), and deterministic — the
    same sequence_index always yields the same variant, so as long as the
    index is computed once (at scripting time) and stored rather than
    recomputed on every retry, assignment is stable across retries.

    sequence_index should be "how many Shorts have already been assigned a
    variant under this experiment" (0 for the first) — the caller derives
    this by counting existing cta_assignment entries in
    state/short_form_queue.json, not by guessing.
    """
    variant_ids = variant_ids or _VARIANT_ORDER
    return variant_ids[sequence_index % len(variant_ids)]


def assign_variant_by_hash(candidate_id, experiment_id=CTA_LUXURY_EXPERIMENT_ID, variant_ids=None):
    """Deterministic hash-based assignment: same (candidate_id, experiment_id)
    always yields the same variant, with no shared counter needed (safe if
    two candidates are being scripted concurrently/out of order). Not
    perfectly balanced over small samples the way rotation is, but stable
    and reproducible. Prefer assign_variant_by_rotation() when a reliable
    sequence index is available (the normal case); this is the fallback.
    """
    variant_ids = variant_ids or _VARIANT_ORDER
    digest = hashlib.sha256(f"{experiment_id}:{candidate_id}".encode()).hexdigest()
    return variant_ids[int(digest, 16) % len(variant_ids)]


def strip_known_cta(description):
    """Remove a known CTA variant (any of CTA_VARIANTS' exact values) from a
    description, along with its blank-line separator, if present. Idempotent
    input for apply_cta() below.

    Checks the LEADING line first — the current convention (owner direction,
    2026-08-02: the CTA must be the first line of a Shorts description,
    since that's the only part visible in YouTube Shorts' collapsed
    description preview before a viewer taps "more"). Falls back to
    checking the TRAILING line for backward compatibility with descriptions
    written under the original (pre-2026-08-02) last-line convention, so
    re-processing an old description doesn't leave a stale CTA in place.

    Only removes a line that EXACTLY matches a known variant's full text —
    never a substring/fuzzy match — so ordinary description text that
    happens to mention "Luxury" is never touched. Returns the description
    unchanged if no known CTA is found at either end.
    """
    lines = description.split("\n")
    # Leading convention (current): check the first non-empty line.
    start = 0
    while start < len(lines) and lines[start].strip() == "":
        start += 1
    if start < len(lines) and lines[start].strip() in CTA_VARIANTS.values():
        lines = lines[start + 1:]
        while lines and lines[0].strip() == "":
            lines.pop(0)
        return "\n".join(lines)

    # Trailing convention (backward-compat fallback): check the last non-empty line.
    while lines and lines[-1].strip() == "":
        lines.pop()
    if not lines:
        return description
    if lines[-1].strip() in CTA_VARIANTS.values():
        lines.pop()
        while lines and lines[-1].strip() == "":
            lines.pop()
    return "\n".join(lines)


def apply_cta(description, variant_id=DEFAULT_VARIANT_ID):
    """Prepend the given CTA variant as the first line of a Shorts
    description (owner direction, 2026-08-02 — YouTube Shorts only shows
    the first line in its collapsed description preview, so a CTA placed
    last is effectively invisible unless a viewer taps "more"). Idempotent
    and variant-aware: any previously-applied known variant (leading or, for
    backward compatibility, trailing) is stripped first, so calling this
    twice — or once each with two different variants, e.g. on a
    regenerated/retried description — never produces two CTA lines and
    never leaves a stale variant behind a new one.
    """
    if variant_id not in CTA_VARIANTS:
        raise ValueError(f"unknown CTA variant_id: {variant_id!r}")
    base = strip_known_cta(description)
    cta_text = CTA_VARIANTS[variant_id]
    separator = "\n\n" if base.strip() else ""
    return f"{cta_text}{separator}{base}"


def cta_metadata(variant_id, experiment_id=CTA_LUXURY_EXPERIMENT_ID):
    """The small internal tracking record (owner spec section 6, "CTA
    Tracking") to store on the candidate's queue entry — never placed in
    the public description itself, only in state/short_form_queue.json /
    state/posted_history.json for later analytics joins."""
    if variant_id not in CTA_VARIANTS:
        raise ValueError(f"unknown CTA variant_id: {variant_id!r}")
    return {
        "cta_experiment_id": experiment_id,
        "cta_variant_id": variant_id,
        "cta_text": CTA_VARIANTS[variant_id],
    }
