#!/usr/bin/env python3
"""One-off driver: publish the current ready_to_publish backlog in schedule
order, stopping immediately on any uploadLimitExceeded. Not a permanent
pipeline script -- ad hoc for clearing the pre-2026-08-04 batch backlog."""
import json
import subprocess
import sys

STATE = "state"


def load(name):
    with open(f"{STATE}/{name}.json") as f:
        return json.load(f)


def save(name, data):
    with open(f"{STATE}/{name}.json", "w") as f:
        json.dump(data, f, indent=2)


def main():
    sfq = load("short_form_queue")
    lfq = load("long_form_queue")
    wbp = load("weekly_batch_progress")
    ph = load("posted_history")

    sf_by_id = {x["id"]: x for x in sfq["queue"]}
    lf_by_id = {x["id"]: x for x in lfq["queue"]}

    ready = [it for it in wbp["current_batch"]["items"] if it["status"] == "ready_to_publish"]
    ready.sort(key=lambda x: x["scheduled_publish_at"])

    for it in ready:
        cid = it["candidate_id"]
        fmt = it["format"]
        publish_at = it["scheduled_publish_at"]
        print(f"\n=== item {it['index']}: {fmt} {cid} @ {publish_at} ===", flush=True)

        if fmt == "short":
            c = sf_by_id[cid]
            file_path = f"assets/short-form-clips/processed/{cid}.mp4"
            thumb_path = f"assets/short-form-clips/processed/{cid}_thumb.jpg"
            cta = (c.get("cta_assignment") or {}).get("cta_variant_id", "cta_luxury_control")
            cmd = [
                "python3", "scripts/youtube_upload.py",
                "--file", file_path,
                "--title", c["title_pattern"],
                "--description", c["seo_description"],
                "--tags", ",".join(c.get("tags", [])),
                "--category", "22",
                "--privacy", "public",
                "--publish-at", publish_at,
                "--thumbnail", thumb_path,
                "--short",
                "--cta-variant", cta,
            ]
        else:
            c = lf_by_id[cid]
            file_path = c["final_video_path"]
            thumb_path = c.get("thumbnail_path") or f"assets/long-form/thumbnails/{cid}_thumb.jpg"
            cmd = [
                "python3", "scripts/youtube_upload.py",
                "--file", file_path,
                "--title", c["title"],
                "--description", c["seo_description"],
                "--tags", ",".join(c.get("tags", [])),
                "--category", "10",
                "--privacy", "public",
                "--publish-at", publish_at,
                "--thumbnail", thumb_path,
            ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        out = result.stdout.strip()
        err = result.stderr.strip()
        print(out)
        if err:
            print("STDERR:", err, file=sys.stderr)

        if "uploadLimitExceeded" in out or "uploadLimitExceeded" in err:
            print(f"\n!!! QUOTA HIT at item {it['index']} ({cid}) -- stopping, no retry.")
            it["status"] = "ready_to_publish"
            it["publish_blocker"] = "uploadLimitExceeded -- stopped mid-backlog-clear, see script output"
            save("weekly_batch_progress", wbp)
            sys.exit(1)

        if result.returncode != 0 or "PUBLISHED video_id=" not in out:
            print(f"\n!!! UPLOAD FAILED (non-quota) at item {it['index']} ({cid}) -- stopping for manual review.")
            sys.exit(1)

        video_id = out.split("PUBLISHED video_id=")[1].split()[0]

        if fmt == "short":
            c["status"] = "published"
            ph.setdefault("short_form", []).append({
                "candidate_id": cid,
                "video_id": video_id,
                "published_at": publish_at,
                "title": c["title_pattern"],
            })
        else:
            c["status"] = "published"
            ph.setdefault("long_form", []).append({
                "candidate_id": cid,
                "video_id": video_id,
                "published_at": publish_at,
                "title": c["title"],
                "format": "long",
                "duration_minutes": c.get("actual_duration_minutes"),
            })

        it["status"] = "done"

        save("short_form_queue", sfq)
        save("long_form_queue", lfq)
        save("posted_history", ph)
        save("weekly_batch_progress", wbp)

        print(f"Recorded {cid} -> {video_id}")

    print("\nAll ready_to_publish items processed successfully.")


if __name__ == "__main__":
    main()
