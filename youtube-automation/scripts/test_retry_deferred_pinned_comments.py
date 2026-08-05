#!/usr/bin/env python3
"""Focused test for scripts/retry_deferred_pinned_comments.py's needs_retry()
classifier (owner direction, 2026-08-05 analytics-cycle fix for the
Shorts->long-form pinned-comment funnel). No pytest dependency in this
project -- run directly:
  python3 scripts/test_retry_deferred_pinned_comments.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from retry_deferred_pinned_comments import needs_retry

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


def test_needs_retry():
    print("needs_retry() classification")
    check("deferred_until_public status needs retry", needs_retry("deferred_until_public"))
    check(
        "'not yet public' failure message needs retry",
        needs_retry("failed: 403 forbidden (commentThreads insufficient permissions -- likely video still private/scheduled, not yet public)"),
    )
    check("'not attempted this pass' needs retry", needs_retry("not attempted this pass"))
    check(
        "generic 403 forbidden needs retry",
        needs_retry("failed: 403 forbidden (commentThreads insufficient permissions)"),
    )
    check("a real successful post does not need retry", not needs_retry("posted (comment_id=abc123)"))
    check(
        "a retried-and-posted status does not need retry",
        not needs_retry("posted (retried after going public; comment_id=abc123)"),
    )
    check("None status does not need retry", not needs_retry(None))
    check("empty string does not need retry", not needs_retry(""))
    check(
        "scope-unavailable skip does not need retry (different problem, not a privacy-timing issue)",
        not needs_retry("SKIPPED: comment-posting credentials unavailable"),
    )


if __name__ == "__main__":
    test_needs_retry()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
