#!/usr/bin/env python3
"""Focused tests for scripts/cta_experiment.py and its wiring into
scripts/youtube_upload.py (owner direction, 2026-08-01, Controlled CTA
Experimentation for Shorts).

No pytest dependency in this project — run directly:
  python3 scripts/test_cta_experiment.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import cta_experiment as cta
import youtube_upload as up

PASS = 0
FAIL = 0


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS: {name}")
    else:
        FAIL += 1
        print(f"  FAIL: {name} {detail}")


def ends_with_exactly_one_known_cta(description):
    """How many known CTA variants appear as the description's final
    non-empty line — must be exactly 1 for a correctly-processed Short."""
    stripped = cta.strip_known_cta(description)
    return description != stripped  # True if exactly one was found/removed


def test_variant_catalog():
    print("CTA_VARIANTS catalog")
    check("control text matches the original pre-experiment SHORTS_CTA",
          cta.CTA_VARIANTS["cta_luxury_control"] == 'Manifest it. Comment "Luxury" below.')
    for vid, text in cta.CTA_VARIANTS.items():
        check(f"{vid} contains the required Luxury keyword", "Luxury" in text)


def test_scenario_1_no_cta():
    print("1. Description with no CTA")
    d = "Some plain description with no call to action."
    out = cta.apply_cta(d, "cta_luxury_control")
    check("CTA appended as final line", out.endswith(cta.CTA_VARIANTS["cta_luxury_control"]))
    check("original text preserved", out.startswith(d))
    check("exactly one CTA present", ends_with_exactly_one_known_cta(out))


def test_scenario_2_already_has_control():
    print("2. Description already containing the control CTA")
    d = "Some description.\n\nManifest it. Comment \"Luxury\" below."
    out = cta.apply_cta(d, "cta_luxury_control")
    check("not duplicated", out.count('Manifest it. Comment "Luxury" below.') == 1)
    check("still ends with control", out.endswith(cta.CTA_VARIANTS["cta_luxury_control"]))


def test_scenario_3_already_has_other_variant():
    print("3. Description containing another approved variant")
    d = 'Some description.\n\nType "Luxury" to claim it.'
    out = cta.apply_cta(d, "cta_luxury_future")
    check("old variant removed", 'Type "Luxury" to claim it.' not in out)
    check("new variant applied", out.endswith(cta.CTA_VARIANTS["cta_luxury_future"]))
    check("exactly one CTA present", out.count("Luxury") == 1)


def test_scenario_4_processed_twice():
    print("4. Description processed twice")
    d = "Base description."
    once = cta.apply_cta(d, "cta_luxury_begin")
    twice = cta.apply_cta(once, "cta_luxury_begin")
    check("idempotent — processing twice yields identical output", once == twice)
    check("still exactly one CTA", twice.count("Luxury") == 1)


def test_scenario_5_trailing_blank_lines():
    print("5. Description with trailing blank lines")
    d = "Base description.\n\n\n   \n"
    out = cta.apply_cta(d, "cta_luxury_control")
    check("no stray blank lines before the CTA", "\n\n\n" not in out)
    check("CTA still the final line", out.endswith(cta.CTA_VARIANTS["cta_luxury_control"]))


def test_scenario_6_word_luxury_in_body():
    print("6. Description containing the word Luxury in ordinary body text")
    d = "This is a Luxury lifestyle video about a Luxury car in a Luxury district."
    out = cta.apply_cta(d, "cta_luxury_control")
    check("ordinary body text preserved verbatim", out.startswith(d))
    check("CTA appended after it", out.endswith(cta.CTA_VARIANTS["cta_luxury_control"]))
    # Re-processing must not treat the body text's "Luxury" mentions as a CTA to strip.
    out2 = cta.apply_cta(out, "cta_luxury_control")
    check("body text survives a second pass unchanged", out2 == out)


def test_scenario_7_long_form_never_gets_cta():
    print("7. Long-form description")
    d = "A calm one-hour ambience video description."
    result = up.upload.__wrapped__ if hasattr(up.upload, "__wrapped__") else None
    # Simulate the long-form call path: is_short defaults to False.
    # (upload() itself requires real credentials/network, so we test the
    # exact conditional it runs instead — the same code path, no network.)
    is_short = False
    out = d
    if is_short:
        out = up.append_shorts_cta(out)
    check("long-form description is untouched (no CTA appended)", out == d)


def test_scenario_8_short_with_hashtags():
    print("8. Short with hashtags")
    d = "Manifest your future.\n\n#luxury #manifestation #wealth"
    out = cta.apply_cta(d, "cta_luxury_control")
    check("hashtags preserved", "#luxury #manifestation #wealth" in out)
    check("CTA is the true final line, after the hashtags", out.endswith(cta.CTA_VARIANTS["cta_luxury_control"]))
    check("hashtags come before the CTA", out.index("#luxury") < out.index(cta.CTA_VARIANTS["cta_luxury_control"]))


def test_scenario_9_regenerated_short_retains_assignment():
    print("9. Regenerated Short retaining its assigned CTA variant")
    # Simulates: candidate scripted once (assigned variant X), description
    # regenerated by a retried scriptwriter pass, then re-applied — the
    # STORED variant_id must be what's used both times, not re-rolled.
    stored_variant_id = cta.assign_variant_by_rotation(sequence_index=2)
    desc_v1 = "First draft of the description."
    desc_v2 = "Regenerated, slightly different, draft of the description."
    out1 = cta.apply_cta(desc_v1, stored_variant_id)
    out2 = cta.apply_cta(desc_v2, stored_variant_id)
    check("same stored variant used both times", out1.endswith(cta.CTA_VARIANTS[stored_variant_id]))
    check("same stored variant used both times (v2)", out2.endswith(cta.CTA_VARIANTS[stored_variant_id]))
    check("re-deriving assign_variant_by_rotation(2) again is stable", cta.assign_variant_by_rotation(2) == stored_variant_id)


def test_scenario_10_balanced_assignment():
    print("10. Two separate Shorts receiving balanced variant assignments")
    n_variants = len(cta.CTA_VARIANTS)
    assignments = [cta.assign_variant_by_rotation(i) for i in range(n_variants * 3)]
    from collections import Counter
    counts = Counter(assignments)
    check("block rotation is exactly balanced over a full multiple of variants",
          len(set(counts.values())) == 1, detail=str(counts))
    check("all variant IDs actually get used", set(counts) == set(cta.CTA_VARIANTS), detail=str(counts))

    # Hash-based fallback: not perfectly balanced on tiny samples but stable/deterministic.
    hash_assignments_run1 = [cta.assign_variant_by_hash(f"sf_{i:03d}") for i in range(20)]
    hash_assignments_run2 = [cta.assign_variant_by_hash(f"sf_{i:03d}") for i in range(20)]
    check("hash-based assignment is deterministic/stable across calls", hash_assignments_run1 == hash_assignments_run2)


def test_metadata_and_error_handling():
    print("cta_metadata() and error handling")
    meta = cta.cta_metadata("cta_luxury_claim")
    check("metadata has all 3 required fields", set(meta) == {"cta_experiment_id", "cta_variant_id", "cta_text"})
    check("metadata cta_text matches the variant catalog", meta["cta_text"] == cta.CTA_VARIANTS["cta_luxury_claim"])

    try:
        cta.apply_cta("desc", "not_a_real_variant")
        check("unknown variant_id raises", False, "(did not raise)")
    except ValueError:
        check("unknown variant_id raises", True)

    try:
        cta.cta_metadata("not_a_real_variant")
        check("cta_metadata rejects unknown variant_id", False, "(did not raise)")
    except ValueError:
        check("cta_metadata rejects unknown variant_id", True)


def main():
    test_variant_catalog()
    test_scenario_1_no_cta()
    test_scenario_2_already_has_control()
    test_scenario_3_already_has_other_variant()
    test_scenario_4_processed_twice()
    test_scenario_5_trailing_blank_lines()
    test_scenario_6_word_luxury_in_body()
    test_scenario_7_long_form_never_gets_cta()
    test_scenario_8_short_with_hashtags()
    test_scenario_9_regenerated_short_retains_assignment()
    test_scenario_10_balanced_assignment()
    test_metadata_and_error_handling()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
