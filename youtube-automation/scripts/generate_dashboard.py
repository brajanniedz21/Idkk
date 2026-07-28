#!/usr/bin/env python3
"""Generate a static, self-contained, installable-PWA HTML dashboard from
the pipeline's state/*.json files and agents/*.md role docs. No network
calls, no external assets — safe to run anywhere and safe to publish as a
Claude Artifact.

Design: intentionally cheap to run (pure stdlib + PIL for the app icon, no
LLM calls). Meant to be re-run once per daily trigger firing (see
agents/0_orchestrator.md), not after every single item, to keep the
"publish an updated Artifact" step low-cost. Run manually any time with:

    python3 scripts/generate_dashboard.py

Output: dashboard/index.html — a single self-contained file (data: URI
manifest/icons inlined, no service worker) meant to be published via the
Claude Artifact tool. Owner decided (2026-07-28) to keep this Artifact-only
rather than also stand up a separately-hosted installable build (GitHub
Pages would need the repo made public; a Netlify git-integration deploy
was also considered) — so this covers the manifest/icons needed for a
best-effort "Add to Home Screen" on a phone, understanding that on
Android/Chrome this installs as a shortcut (opens in a browser tab), not
a full standalone-launching PWA, since an Artifact can't serve the
separate real files + service worker Chrome requires for that. iOS
Safari's "Add to Home Screen" is closer to app-like out of the box.
"""
import base64
import io
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
AGENTS_DIR = os.path.join(ROOT, "agents")
OUT_DIR = os.path.join(ROOT, "dashboard")


def load(name, default=None):
    path = os.path.join(STATE, name)
    if not os.path.exists(path):
        return default
    with open(path) as f:
        return json.load(f)


def esc(s):
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def fmt_dt(iso):
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%b %-d, %H:%M UTC")
    except Exception:
        return iso


def role_text(md_relpath):
    """Pull the '## Role' paragraph straight out of an agent's own markdown
    doc, so the dashboard can never drift out of sync with the real spec."""
    path = os.path.join(AGENTS_DIR, md_relpath)
    if not os.path.exists(path):
        return "(spec file not found)"
    text = open(path).read()
    m = re.search(r"##\s*Role\s*\n+(.+?)(?=\n##|\Z)", text, re.S)
    if not m:
        return ""
    para = m.group(1).strip()
    para = re.sub(r"\s+", " ", para)
    return para


STATUS_CLASS = {
    "done": "pill-success",
    "published": "pill-success",
    "ready_to_publish": "pill-info",
    "pending": "pill-neutral",
    "scouted": "pill-neutral",
    "scripted": "pill-neutral",
    "produced": "pill-neutral",
    "sound_sourced": "pill-neutral",
    "image_sourced": "pill-neutral",
    "animated": "pill-neutral",
    "quarantined": "pill-critical",
}

STATUS_LABEL = {
    "done": "Published",
    "published": "Published",
    "ready_to_publish": "Ready",
    "pending": "Pending",
    "scouted": "Scouted",
    "scripted": "Scripted",
    "produced": "Produced",
    "sound_sourced": "Sound sourced",
    "image_sourced": "Image sourced",
    "animated": "Animated",
    "quarantined": "Quarantined",
}


def pill(status):
    cls = STATUS_CLASS.get(status, "pill-neutral")
    label = STATUS_LABEL.get(status, status or "—")
    return f'<span class="pill {cls}">{esc(label)}</span>'


# ---------------------------------------------------------------------
# App icon — drawn locally with PIL (no network), a simple "dial" mark in
# the brand's copper accent on the dark ground, used for the PWA manifest
# and Apple touch icon so the dashboard can be added to a home screen.
# ---------------------------------------------------------------------
def make_icon_png_bytes(size):
    from PIL import Image, ImageDraw
    import math

    bg = (16, 18, 26, 255)
    accent = (201, 138, 75, 255)
    accent_dim = (201, 138, 75, 130)

    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = int(size * 0.22)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=bg)

    cx = cy = size / 2
    outer = size * 0.30
    inner = size * 0.11
    d.ellipse(
        [cx - outer, cy - outer, cx + outer, cy + outer],
        outline=accent,
        width=max(2, int(size * 0.045)),
    )
    d.ellipse([cx - inner, cy - inner, cx + inner, cy + inner], fill=accent)
    # a single "needle" tick, like a dial/meter — echoes the batch-progress idea
    ang = math.radians(-55)
    x2 = cx + outer * 1.0 * math.cos(ang)
    y2 = cy + outer * 1.0 * math.sin(ang)
    d.line([cx, cy, x2, y2], fill=accent_dim, width=max(2, int(size * 0.035)))

    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def make_icon_png_b64(size):
    return base64.b64encode(make_icon_png_bytes(size)).decode("ascii")


def main():
    now = datetime.now(timezone.utc)
    channel_path = os.path.join(ROOT, "config", "channel.json")
    channel = json.load(open(channel_path)) if os.path.exists(channel_path) else {}
    handle = channel.get("channel_handle", "@channel")

    dashboard_meta = load("dashboard_artifact.json", {})

    batch = load("weekly_batch_progress.json", {})
    current = (batch or {}).get("current_batch") or {}
    items = current.get("items", [])

    sfq = load("short_form_queue.json", {"queue": []})["queue"]
    lfq = load("long_form_queue.json", {"queue": []})["queue"]

    posted = load("posted_history.json", {"short_form": [], "long_form": []})
    quarantine = load("quarantine.json", {"short_form": [], "long_form": []})
    image_pool = load("image_pool.json", {})

    # ---- KPI counts ----
    status_counts = {"done": 0, "ready_to_publish": 0, "pending": 0}
    for it in items:
        s = it.get("status", "pending")
        status_counts[s] = status_counts.get(s, 0) + 1

    blockers = []
    for c in lfq:
        if c.get("publish_blocker"):
            blockers.append((c["id"], c.get("title", c["id"]), c["publish_blocker"]))

    next_due = None
    for it in sorted(items, key=lambda x: x.get("scheduled_publish_at") or "9999"):
        if it.get("status") == "ready_to_publish":
            next_due = it
            break

    quarantine_count = len(quarantine.get("short_form", [])) + len(
        quarantine.get("long_form", [])
    )

    # ---- Activity log (posted history, newest first) ----
    activity = []
    for v in posted.get("short_form", []):
        activity.append({**v, "kind": "short"})
    for v in posted.get("long_form", []):
        activity.append({**v, "kind": "long"})
    activity.sort(key=lambda v: v.get("published_at", ""), reverse=True)
    activity = activity[:14]

    # ---- Batch grid (day x slot) ----
    days = []
    for it in items:
        d = it.get("day")
        if d and d not in [x["day"] for x in days]:
            days.append({"day": d, "slots": []})
    for it in items:
        for entry in days:
            if entry["day"] == it["day"]:
                entry["slots"].append(it)

    # ---- Image pool ----
    unused_pool = image_pool.get("unused_owner_provided_pool", [])
    pending_images = [e for e in unused_pool if "PENDING" in (e.get("note", "").upper())]
    clean_unused = [e for e in unused_pool if e not in pending_images]

    generated_at = now.strftime("%b %-d, %Y — %H:%M UTC")

    # ---- Agent totals (per-track) ----
    sf_counts = {}
    for c in sfq:
        sf_counts[c.get("status", "?")] = sf_counts.get(c.get("status", "?"), 0) + 1
    lf_counts = {}
    for c in lfq:
        lf_counts[c.get("status", "?")] = lf_counts.get(c.get("status", "?"), 0) + 1
    sf_published = sf_counts.get("published", 0) + sf_counts.get("done", 0)
    sf_quarantined = sf_counts.get("quarantined", 0)
    lf_published = lf_counts.get("published", 0) + lf_counts.get("done", 0)
    lf_quarantined = lf_counts.get("quarantined", 0)

    # ---------------------------------------------------------------
    # Agents
    # ---------------------------------------------------------------
    def agent_card(num, name, md_path, extra=""):
        return f"""
        <div class="agent">
          <div class="agent-head">
            <span class="agent-num mono">{esc(num)}</span>
            <span class="agent-name">{esc(name)}</span>
          </div>
          <p class="agent-role">{esc(role_text(md_path))}</p>
          {extra}
        </div>"""

    sf_agents = "".join([
        agent_card("1.1", "Trend Scout", "short_form/1.1_trend_scout.md"),
        agent_card("2.1", "Scriptwriter", "short_form/2.1_scriptwriter.md"),
        agent_card("3.1", "Producer", "short_form/3.1_producer.md"),
        agent_card_gates(),
        agent_card("4.1", "Publisher", "short_form/4.1_publisher.md"),
    ])

    lf_agents = "".join([
        agent_card("1.2", "Format Scout", "long_form/1.2_format_scout.md"),
        agent_card("2.2", "Image Sourcer", "long_form/2.2_image_sourcer.md"),
        agent_card("3.2", "Animator", "long_form/3.2_animator.md"),
        agent_card("4.2", "Sound Sourcer", "long_form/4.2_sound_sourcer.md"),
        agent_card("5", "Assembler / Looper", "long_form/5_assembler.md"),
        agent_card("6", "Publisher", "long_form/6_publisher.md"),
    ])

    orchestrator_role = role_text("0_orchestrator.md")

    # ---------------------------------------------------------------
    # HTML fragments
    # ---------------------------------------------------------------
    def kpi_tile(label, value, sub="", tone="neutral"):
        return f"""
        <div class="kpi kpi-{tone}">
          <div class="kpi-value">{value}</div>
          <div class="kpi-label">{esc(label)}</div>
          {f'<div class="kpi-sub">{esc(sub)}</div>' if sub else ''}
        </div>"""

    kpis = "".join([
        kpi_tile("Published this batch", status_counts.get("done", 0), tone="success"),
        kpi_tile("Ready to publish", status_counts.get("ready_to_publish", 0), tone="info"),
        kpi_tile("Still pending", status_counts.get("pending", 0), tone="neutral"),
        kpi_tile(
            "Quarantined (all-time)",
            quarantine_count,
            tone="critical" if quarantine_count else "neutral",
        ),
        kpi_tile(
            "Next scheduled",
            fmt_dt(next_due["scheduled_publish_at"]) if next_due else "—",
            sub=(next_due.get("candidate_id", "") if next_due else ""),
            tone="info",
        ),
    ])

    grid_rows = []
    slot_order = {"09:00": 0, "14:00": 1, "19:00": 2, "20:00": 3}
    for entry in days:
        slots = sorted(entry["slots"], key=lambda s: slot_order.get(s.get("local_slot"), 9))
        cells = []
        for s in slots:
            fmt = s.get("format")
            cid = s.get("candidate_id") or "—"
            cls = STATUS_CLASS.get(s.get("status"), "pill-neutral")
            cells.append(
                f'<div class="slot {cls}" title="{esc(cid)} · {esc(s.get("status"))}">'
                f'<span class="slot-time">{esc(s.get("local_slot",""))}</span>'
                f'<span class="slot-fmt">{"Short" if fmt=="short" else "Long"}</span>'
                f'<span class="slot-id">{esc(cid)}</span>'
                f"</div>"
            )
        grid_rows.append(
            f'<div class="grid-row"><div class="grid-day">{esc(entry["day"])}</div>'
            f'<div class="grid-slots">{"".join(cells)}</div></div>'
        )
    grid_html = "".join(grid_rows) or '<div class="empty">No batch initialized yet.</div>'

    def lf_row(c):
        return (
            f'<tr><td class="mono">{esc(c["id"])}</td>'
            f'<td>{esc(c.get("title","—"))}</td>'
            f'<td>{pill(c.get("status"))}</td>'
            f'<td class="mono">{esc(c.get("target_length_minutes","—"))} min</td>'
            f'<td class="mono muted">{esc(c.get("scouted_at","—")[:10])}</td></tr>'
        )

    lf_rows = "".join(lf_row(c) for c in lfq) or '<tr><td colspan="5" class="empty">No candidates yet.</td></tr>'

    def sf_row(c):
        return (
            f'<tr><td class="mono">{esc(c["id"])}</td>'
            f'<td>{esc(c.get("title","—"))}</td>'
            f'<td>{pill(c.get("status"))}</td>'
            f'<td class="mono muted">{esc((c.get("scripted_at") or c.get("scouted_at") or "—")[:10])}</td></tr>'
        )

    sf_rows = "".join(sf_row(c) for c in sfq) or '<tr><td colspan="4" class="empty">No candidates yet.</td></tr>'

    def activity_row(v):
        icon = "▮" if v["kind"] == "short" else "━"
        url = v.get("url", "#")
        return (
            f'<div class="log-row">'
            f'<span class="log-icon log-{v["kind"]}">{icon}</span>'
            f'<span class="log-time mono">{fmt_dt(v.get("published_at"))}</span>'
            f'<a class="log-title" href="{esc(url)}" target="_blank" rel="noopener">{esc(v.get("title","—"))}</a>'
            f"</div>"
        )

    activity_html = "".join(activity_row(v) for v in activity) or '<div class="empty">Nothing published yet.</div>'

    blocker_html = ""
    if blockers:
        rows = "".join(
            f'<div class="blocker-row"><span class="mono">{esc(bid)}</span> — {esc(title)}<div class="blocker-note">{esc(note)}</div></div>'
            for bid, title, note in blockers
        )
        blocker_html = f'<div class="panel panel-critical"><h3>⚠ Blocked on publish</h3>{rows}</div>'

    # ---- PWA icon + manifest (best-effort "Add to Home Screen") ----
    # Single self-contained build for the Claude Artifact tool — owner
    # decided (2026-07-28) not to stand up a separately-hosted version
    # (would need the repo public for GitHub Pages, or a Netlify git
    # integration), so manifest/icons are inlined as data: URIs. Note this
    # means Android/Chrome will offer "Create shortcut" rather than a full
    # standalone "Install" (that needs real served files + a service
    # worker, which an Artifact can't provide) — iOS Safari's "Add to
    # Home Screen" gets closer to app-like out of the box.
    icon192_b64 = make_icon_png_b64(192)
    icon180_b64 = make_icon_png_b64(180)  # apple-touch-icon

    app_name = f"{handle} Pipeline"
    manifest = {
        "name": app_name,
        "short_name": "Pipeline",
        "description": "Status dashboard for the YouTube automation content pipeline.",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#10121a",
        "theme_color": "#10121a",
        "icons": [
            {"src": f"data:image/png;base64,{icon192_b64}", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    manifest_json = json.dumps(manifest)
    manifest_data_uri = "data:application/manifest+json," + manifest_json.replace("#", "%23")

    pwa_head = f"""<link rel="manifest" href="{manifest_data_uri}" />
<meta name="theme-color" content="#10121a" media="(prefers-color-scheme: dark)" />
<meta name="theme-color" content="#f5f3ef" media="(prefers-color-scheme: light)" />
<meta name="mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
<meta name="apple-mobile-web-app-title" content="Pipeline" />
<link rel="apple-touch-icon" href="data:image/png;base64,{icon180_b64}" />
<link rel="icon" href="data:image/png;base64,{icon192_b64}" />"""

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>{esc(handle)} — Pipeline Dashboard</title>

{pwa_head}

<style>
:root {{
  --bg: #10121a;
  --surface: #191c27;
  --surface-2: #20242f;
  --border: #2b303f;
  --text: #edeef3;
  --text-dim: #8e93a8;
  --text-faint: #5b6070;
  --accent: #c98a4b;
  --success: #4cb17d;
  --info: #6f9bd1;
  --warning: #e0a83e;
  --critical: #e2584b;
  --neutral: #565c70;
  font-variant-numeric: tabular-nums;
}}
:root[data-theme="light"] {{
  --bg: #f5f3ef;
  --surface: #ffffff;
  --surface-2: #f0ede6;
  --border: #ddd7cb;
  --text: #201d18;
  --text-dim: #6b6459;
  --text-faint: #a39c8c;
  --accent: #a9682c;
  --success: #2f8f5f;
  --info: #3b6ea5;
  --warning: #b3811f;
  --critical: #c23f32;
  --neutral: #8a8578;
}}
@media (prefers-color-scheme: light) {{
  :root:not([data-theme="dark"]) {{
    --bg: #f5f3ef;
    --surface: #ffffff;
    --surface-2: #f0ede6;
    --border: #ddd7cb;
    --text: #201d18;
    --text-dim: #6b6459;
    --text-faint: #a39c8c;
    --accent: #a9682c;
    --success: #2f8f5f;
    --info: #3b6ea5;
    --warning: #b3811f;
    --critical: #c23f32;
    --neutral: #8a8578;
  }}
}}
* {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
  line-height: 1.5;
  padding: 20px 16px calc(80px + env(safe-area-inset-bottom));
  padding-left: max(16px, env(safe-area-inset-left));
  padding-right: max(16px, env(safe-area-inset-right));
  padding-top: max(20px, env(safe-area-inset-top));
}}
.mono {{
  font-family: ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", monospace;
}}
.wrap {{ max-width: 1180px; margin: 0 auto; }}
a {{ -webkit-touch-callout: default; }}
header {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--border);
  padding-bottom: 16px;
}}
h1 {{
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.01em;
  margin: 0;
  text-wrap: balance;
}}
h1 .sub {{
  display: block;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text-dim);
  margin-top: 4px;
  letter-spacing: 0;
}}
.updated {{
  font-size: 11.5px;
  color: var(--text-faint);
  text-align: right;
}}
.kpis {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 10px;
  margin-bottom: 28px;
}}
.kpi {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  border-top: 2px solid var(--neutral);
}}
.kpi-success {{ border-top-color: var(--success); }}
.kpi-info {{ border-top-color: var(--info); }}
.kpi-critical {{ border-top-color: var(--critical); }}
.kpi-value {{
  font-size: 24px;
  font-weight: 700;
  font-family: ui-monospace, "SF Mono", monospace;
}}
.kpi-label {{
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 2px;
}}
.kpi-sub {{
  font-size: 11px;
  color: var(--text-faint);
  margin-top: 4px;
  font-family: ui-monospace, monospace;
  word-break: break-word;
}}
h2 {{
  font-size: 13px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  margin: 32px 0 12px;
}}
h2 .h2-note {{
  text-transform: none;
  letter-spacing: 0;
  font-weight: 500;
  color: var(--text-faint);
  font-size: 11.5px;
}}
.panel {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  margin-bottom: 16px;
}}
.panel-critical {{ border-color: color-mix(in srgb, var(--critical) 40%, var(--border)); }}
.panel h3 {{ margin: 0 0 8px; font-size: 13px; color: var(--critical); }}
.blocker-row {{ font-size: 13px; padding: 6px 0; border-top: 1px solid var(--border); }}
.blocker-row:first-child {{ border-top: none; }}
.blocker-note {{ color: var(--text-dim); font-size: 12px; margin-top: 2px; }}

.grid {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  padding: 6px;
}}
.grid-row {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}}
.grid-row:last-child {{ border-bottom: none; }}
.grid-day {{
  width: 78px;
  flex-shrink: 0;
  font-family: ui-monospace, monospace;
  font-size: 12px;
  color: var(--text-dim);
}}
.grid-slots {{ display: flex; gap: 8px; }}
.slot {{
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 6px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  min-width: 88px;
  flex-shrink: 0;
  font-size: 11px;
}}
.slot-time {{ color: var(--text-faint); font-family: ui-monospace, monospace; }}
.slot-fmt {{ font-weight: 600; }}
.slot-id {{ color: var(--text-dim); font-family: ui-monospace, monospace; font-size: 10.5px; }}

table {{ width: 100%; border-collapse: collapse; font-size: 12.5px; }}
th {{
  text-align: left;
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--text-faint);
  font-weight: 600;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}}
td {{ padding: 9px 10px; border-bottom: 1px solid var(--border); }}
tr:last-child td {{ border-bottom: none; }}
.table-wrap {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}}
.muted {{ color: var(--text-faint); }}
.empty {{ color: var(--text-faint); padding: 18px; text-align: center; }}

.pill {{
  display: inline-block;
  font-size: 10.5px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 999px;
  letter-spacing: 0.01em;
  white-space: nowrap;
}}
.pill-success {{ background: color-mix(in srgb, var(--success) 18%, transparent); color: var(--success); }}
.pill-info {{ background: color-mix(in srgb, var(--info) 18%, transparent); color: var(--info); }}
.pill-critical {{ background: color-mix(in srgb, var(--critical) 18%, transparent); color: var(--critical); }}
.pill-neutral {{ background: color-mix(in srgb, var(--neutral) 22%, transparent); color: var(--text-dim); }}

.cols2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
@media (max-width: 760px) {{ .cols2 {{ grid-template-columns: 1fr; }} }}

.log {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 6px 4px;
}}
.log-row {{
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  column-gap: 10px;
  row-gap: 2px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
}}
.log-row:last-child {{ border-bottom: none; }}
.log-icon.log-short {{ color: var(--accent); }}
.log-icon.log-long {{ color: var(--info); }}
.log-time {{ font-size: 11px; color: var(--text-faint); }}
.log-title {{ color: var(--text); text-decoration: none; flex: 1 1 200px; min-width: 0; }}
.log-title:hover {{ color: var(--accent); text-decoration: underline; }}

.track {{ margin-bottom: 22px; }}
.track-head {{
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 10px;
  flex-wrap: wrap;
  gap: 6px;
}}
.track-title {{ font-size: 13.5px; font-weight: 700; }}
.track-stats {{ font-size: 11.5px; color: var(--text-faint); font-family: ui-monospace, monospace; }}
.agent-row {{
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 10px;
}}
.agent {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 13px 14px;
  border-left: 2px solid var(--accent);
}}
.agent-gates {{ border-left-color: var(--warning); }}
.agent-head {{ display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }}
.agent-num {{
  font-size: 10.5px;
  color: var(--accent);
  background: color-mix(in srgb, var(--accent) 16%, transparent);
  padding: 2px 6px;
  border-radius: 5px;
}}
.agent-gates .agent-num {{ color: var(--warning); background: color-mix(in srgb, var(--warning) 16%, transparent); }}
.agent-name {{ font-size: 13px; font-weight: 700; }}
.agent-role {{ font-size: 12px; color: var(--text-dim); margin: 0; line-height: 1.5; }}

.orchestrator {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  margin-bottom: 24px;
  border-top: 2px solid var(--accent);
}}
.orchestrator-head {{ font-size: 13.5px; font-weight: 700; margin-bottom: 6px; }}
.orchestrator p {{ font-size: 12.5px; color: var(--text-dim); margin: 0; line-height: 1.55; }}

footer {{
  margin-top: 36px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-faint);
  padding-bottom: env(safe-area-inset-bottom);
}}

@media (max-width: 480px) {{
  body {{ padding-left: 12px; padding-right: 12px; }}
  h1 {{ font-size: 18px; }}
  .kpis {{ grid-template-columns: repeat(2, 1fr); }}
  .agent-row {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{esc(handle)}
      <span class="sub">YouTube automation pipeline — daily batch dashboard</span>
    </h1>
    <div class="updated">Generated {esc(generated_at)}<br/>Redeployed once per daily cycle</div>
  </header>

  <div class="kpis">{kpis}</div>

  {blocker_html}

  <h2>This week's batch</h2>
  <div class="grid">{grid_html}</div>

  <h2>Pipeline agents <span class="h2-note">— live from agents/*.md</span></h2>

  <div class="orchestrator">
    <div class="orchestrator-head">Agent 0 — Orchestrator</div>
    <p>{esc(orchestrator_role)}</p>
  </div>

  <div class="track">
    <div class="track-head">
      <div class="track-title">Short-form track</div>
      <div class="track-stats mono">{len(sfq)} total · {sf_published} published · {sf_quarantined} quarantined</div>
    </div>
    <div class="agent-row">{sf_agents}</div>
  </div>

  <div class="track">
    <div class="track-head">
      <div class="track-title">Long-form track</div>
      <div class="track-stats mono">{len(lfq)} total · {lf_published} published · {lf_quarantined} quarantined</div>
    </div>
    <div class="agent-row">{lf_agents}</div>
  </div>

  <h2>Queues</h2>
  <div class="cols2">
    <div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:6px;">Long-form ({len(lfq)})</div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Length</th><th>Scouted</th></tr></thead>
          <tbody>{lf_rows}</tbody>
        </table>
      </div>
    </div>
    <div>
      <div style="font-size:12px;color:var(--text-dim);margin-bottom:6px;">Short-form ({len(sfq)})</div>
      <div class="table-wrap" style="max-height:420px;overflow-y:auto;-webkit-overflow-scrolling:touch;">
        <table>
          <thead><tr><th>ID</th><th>Title</th><th>Status</th><th>Date</th></tr></thead>
          <tbody>{sf_rows}</tbody>
        </table>
      </div>
    </div>
  </div>

  <h2>Recently published</h2>
  <div class="log">{activity_html}</div>

  <footer>
    Pipeline state read from <span class="mono">state/*.json</span> and agent specs from <span class="mono">agents/*.md</span> at generation time · quarantined items: {quarantine_count} · image pool clean/unused: {len(clean_unused)}, pending vet: {len(pending_images)}<br/>
    Tip: open this page in your phone's browser (not the Claude app) and use "Add to Home Screen" / "Install".
  </footer>
</div>
</body>
</html>
"""

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "index.html")
    with open(out_path, "w") as f:
        f.write(html)
    print("wrote", out_path, f"({len(html)} bytes)")


def agent_card_gates():
    gates_role = (
        "Every candidate must pass the shared and format-specific gates in "
        "config/gates.json before it can move to ready_to_publish — factual/"
        "controversy screen, platform policy check, basic QA, copyright "
        "mitigation, and audio license check. A failing candidate is "
        "quarantined with a logged reason and the next candidate is scouted "
        "instead; gates are never lowered to hit the publishing schedule."
    )
    return f"""
        <div class="agent agent-gates">
          <div class="agent-head">
            <span class="agent-num mono">—</span>
            <span class="agent-name">Gates</span>
          </div>
          <p class="agent-role">{esc(gates_role)}</p>
        </div>"""


if __name__ == "__main__":
    main()
