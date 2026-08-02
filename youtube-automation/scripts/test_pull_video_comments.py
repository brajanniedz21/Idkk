#!/usr/bin/env python3
"""Focused tests for scripts/pull_video_comments.py's automated-vs-organic
comment classification (owner direction, 2026-08-02).

No pytest dependency in this project — run directly:
  python3 scripts/test_pull_video_comments.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import pull_video_comments as pvc

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


CHANNEL_ID = "UCfTbwJxMPqL004V8Ssc5eWQ"


def test_channel_own_comment_with_known_text_is_automated():
    print("1. Channel's own comment with a known automated text is classified automated")
    c = {"authorChannelId": {"value": CHANNEL_ID}, "textOriginal": "Manifest with ambience, full videos on my channel."}
    check("classified automated", pvc.is_automated_comment(c, CHANNEL_ID) is True)


def test_organic_viewer_comment_is_not_automated():
    print("2. A real viewer's comment is never classified automated")
    c = {"authorChannelId": {"value": "UC9PAeYH1vMkOGmooFAYErTw"}, "textOriginal": "This is incredible!"}
    check("classified organic", pvc.is_automated_comment(c, CHANNEL_ID) is False)


def test_channel_comment_with_unknown_text_is_not_automated():
    print("3. Channel owner's own comment with UNKNOWN text is not misclassified as automated")
    c = {"authorChannelId": {"value": CHANNEL_ID}, "textOriginal": "Thanks so much for watching everyone!"}
    check("real reply from the channel owner stays organic, not silently absorbed", pvc.is_automated_comment(c, CHANNEL_ID) is False)


def test_viewer_typing_the_same_text_is_not_automated():
    print("4. A viewer typing the exact same words as the automated comment is NOT misclassified (author must also match)")
    c = {"authorChannelId": {"value": "UCsomeoneelse"}, "textOriginal": "Manifest with ambience, full videos on my channel."}
    check("author mismatch keeps it organic", pvc.is_automated_comment(c, CHANNEL_ID) is False)


def test_luxury_keyword_detection_case_insensitive():
    print("5. pull_comments_for_video's organic_comments_mentioning_luxury logic is case-insensitive")
    check("'Luxury' matches lowercase check", "luxury" in "Luxury is my future!".lower())
    check("'LUXURY' matches lowercase check", "luxury" in "LUXURY!!!".lower())


def main():
    test_channel_own_comment_with_known_text_is_automated()
    test_organic_viewer_comment_is_not_automated()
    test_channel_comment_with_unknown_text_is_not_automated()
    test_viewer_typing_the_same_text_is_not_automated()
    test_luxury_keyword_detection_case_insensitive()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
