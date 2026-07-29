#!/usr/bin/env python3
"""One-off driver: sequentially publish a list of ready_to_publish candidates,
updating state after each success, stopping (not retrying) on the first
uploadLimitExceeded. Owner explicitly requested pushing through the normal
daily cap this run (2026-07-29) — this is not the standard daily-trigger path."""
import json
import subprocess
import sys
from datetime import datetime, timezone

ROOT = "/home/user/Idkk/youtube-automation"
IDS = ["sf_019", "sf_020", "sf_021", "lf_005", "sf_022", "sf_023", "sf_024", "lf_006",
       "sf_025", "sf_026", "sf_027", "sf_028", "sf_029", "sf_030", "lf_008"]


def load(name):
    with open(f"{ROOT}/state/{name}") as f:
        return json.load(f)


def save(name, data):
    with open(f"{ROOT}/state/{name}", "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    sfq = load("short_form_queue.json")
    lfq = load("long_form_queue.json")
    posted = load("posted_history.json")
    batch = load("weekly_batch_progress.json")
    by_id = {c["id"]: c for c in sfq["queue"] + lfq["queue"]}
    item_by_cid = {it.get("candidate_id"): it for it in batch["current_batch"]["items"]}

    results = []
    for cid in IDS:
        c = by_id[cid]
        path = c.get("final_video_path") or c.get("produced_file_path") or c.get("video_path")
        fmt = "long" if cid.startswith("lf") else "short"
        item = item_by_cid.get(cid)
        publish_at = item["scheduled_publish_at"] if item else None

        cmd = [
            "python3", f"{ROOT}/scripts/youtube_upload.py",
            "--file", path,
            "--title", c["title"],
            "--description", c.get("seo_description", ""),
            "--tags", ",".join(c.get("tags", [])),
            "--privacy", "public",
        ]
        if publish_at:
            cmd += ["--publish-at", publish_at]

        print(f"=== Uploading {cid} ({fmt}) -> {publish_at} ===", flush=True)
        proc = subprocess.run(cmd, capture_output=True, text=True)
        stdout, stderr = proc.stdout.strip(), proc.stderr.strip()
        print(stdout, flush=True)
        if stderr:
            print(stderr, flush=True)

        if proc.returncode == 0 and "PUBLISHED" in stdout:
            video_id = stdout.split("video_id=")[1].split(" ")[0]
            url = f"https://youtu.be/{video_id}"
            c["status"] = "published"
            c["video_id"] = video_id
            c["video_url"] = url
            posted["long_form" if fmt == "long" else "short_form"].append({
                "video_id": video_id, "url": url, "title": c["title"],
                "published_at": publish_at, "format": fmt,
            })
            if item:
                item["status"] = "done"
            results.append((cid, "PUBLISHED", url))
            save("short_form_queue.json", sfq)
            save("long_form_queue.json", lfq)
            save("posted_history.json", posted)
            save("weekly_batch_progress.json", batch)
            subprocess.run(["git", "add", "-A"], cwd=ROOT)
            subprocess.run(["git", "commit", "-m", f"Publish {cid} ({fmt}) — batch push-through 2026-07-29",
                             "--quiet"], cwd=ROOT)
            print(f"=== {cid} committed locally ===", flush=True)
        else:
            reason = stderr or stdout or f"exit code {proc.returncode}"
            print(f"=== {cid} FAILED: {reason} ===", flush=True)
            if item:
                c["publish_blocker"] = f"Batch push-through attempt {datetime.now(timezone.utc).isoformat()}: {reason}"
                save("short_form_queue.json", sfq)
                save("long_form_queue.json", lfq)
                subprocess.run(["git", "add", "-A"], cwd=ROOT)
                subprocess.run(["git", "commit", "-m", f"{cid}: publish blocked ({reason[:80]})", "--quiet"], cwd=ROOT)
            results.append((cid, "FAILED", reason))
            if "uploadLimitExceeded" in reason:
                print("=== uploadLimitExceeded hit — stopping, not retrying ===", flush=True)
                break

    print("\n=== SUMMARY ===", flush=True)
    for cid, status, detail in results:
        print(f"{cid}: {status} {detail}", flush=True)
    print("DRIVER_DONE", flush=True)


if __name__ == "__main__":
    main()
