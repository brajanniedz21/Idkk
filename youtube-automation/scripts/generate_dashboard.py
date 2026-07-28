#!/usr/bin/env python3
"""Generate a static, self-contained, iOS-style tabbed HTML dashboard from
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
rather than also stand up a separately-hosted installable build — so this
covers the manifest/icons needed for a best-effort "Add to Home Screen" on
a phone, understanding that on Android/Chrome this installs as a shortcut
(opens in a browser tab), not a full standalone-launching PWA, since an
Artifact can't serve the separate real files + service worker Chrome
requires for that. iOS Safari's "Add to Home Screen" is closer to
app-like out of the box, which is also why the UI itself (updated
2026-07-28, owner request) follows iOS Human Interface Guidelines: a
bottom tab bar, grouped inset lists, large titles, and iOS system colors.
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


def fmt_day(iso):
    if not iso:
        return "—"
    try:
        dt = datetime.fromisoformat(iso)
        return dt.strftime("%a, %b %-d")
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


# Status -> (short label, semantic tone). Tone drives pill color only —
# never the row's leading icon bubble, which encodes *what* the row is,
# not its current state.
STATUS_META = {
    "done": ("Published", "success"),
    "published": ("Published", "success"),
    "ready_to_publish": ("Ready", "info"),
    "pending": ("Pending", "neutral"),
    "scouted": ("Scouted", "neutral"),
    "scripted": ("Scripted", "neutral"),
    "produced": ("Produced", "neutral"),
    "sound_sourced": ("Sound sourced", "neutral"),
    "image_sourced": ("Image sourced", "neutral"),
    "animated": ("Animated", "neutral"),
    "quarantined": ("Quarantined", "critical"),
}


def pill(status):
    label, tone = STATUS_META.get(status, (status or "—", "neutral"))
    return f'<span class="pill pill-{tone}">{esc(label)}</span>'


# ---------------------------------------------------------------------
# Inline icons — small stroke-based glyphs in the SF Symbols spirit
# (no icon font/CDN available inside an Artifact's CSP, so these are
# hand-drawn SVG paths at a consistent 24x24 grid, 1.7-1.9 stroke weight).
# ---------------------------------------------------------------------
def icon(name, size=24):
    paths = {
        "gauge": '<circle cx="12" cy="12" r="9"/><path d="M12 12 L16 8"/><path d="M8 15a5 5 0 0 1 8 0" stroke-linecap="round"/>',
        "agents": '<circle cx="9" cy="9" r="3.2"/><circle cx="16.5" cy="10.5" r="2.4"/><path d="M4 19c0-2.9 2.4-5 5-5s5 2.1 5 5"/><path d="M14.5 14.6c2.2.2 4 1.9 4 4.4"/>',
        "queues": '<path d="M4 6h16" stroke-linecap="round"/><path d="M4 12h16" stroke-linecap="round"/><path d="M4 18h10" stroke-linecap="round"/>',
        "activity": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2" stroke-linecap="round" stroke-linejoin="round"/>',
        "chevron": '<path d="M9 5l6 7-6 7" stroke-linecap="round" stroke-linejoin="round"/>',
        "warn": '<path d="M12 4 2.5 20h19L12 4Z" stroke-linejoin="round"/><path d="M12 10.5v4.2" stroke-linecap="round"/><circle cx="12" cy="17.3" r="0.9" fill="currentColor" stroke="none"/>',
        "check": '<path d="M4.5 12.5l5 5 10-11" stroke-linecap="round" stroke-linejoin="round"/>',
    }
    d = paths.get(name, "")
    return (
        f'<svg viewBox="0 0 24 24" width="{size}" height="{size}" fill="none" '
        f'stroke="currentColor" stroke-width="1.8">{d}</svg>'
    )


ICON_TONE = {
    "trend_scout": "accent",
    "scriptwriter": "accent",
    "producer": "accent",
    "gates": "warning",
    "publisher": "success",
    "format_scout": "info",
    "image_sourcer": "info",
    "animator": "info",
    "sound_sourcer": "info",
    "assembler": "info",
    "orchestrator": "accent",
}


def icon_bubble(letter_or_icon, tone="accent", is_svg=False):
    inner = letter_or_icon if is_svg else f'<span>{esc(letter_or_icon)}</span>'
    return f'<div class="row-icon row-icon-{tone}">{inner}</div>'


# ---------------------------------------------------------------------
# App icon — drawn locally with PIL (no network), a simple "dial" mark in
# the brand's copper accent on the dark ground, used for the PWA manifest
# and Apple touch icon so the dashboard can be added to a home screen.
# ---------------------------------------------------------------------
def make_icon_png_bytes(size):
    from PIL import Image, ImageDraw
    import math

    bg = (0, 0, 0, 255)
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

    quarantine_count = len(quarantine.get("short_form", [])) + len(quarantine.get("long_form", []))

    # ---- Activity log (posted history, newest first) ----
    activity = []
    for v in posted.get("short_form", []):
        activity.append({**v, "kind": "short"})
    for v in posted.get("long_form", []):
        activity.append({**v, "kind": "long"})
    activity.sort(key=lambda v: v.get("published_at", ""), reverse=True)
    activity = activity[:20]

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
    sf_counts, lf_counts = {}, {}
    for c in sfq:
        sf_counts[c.get("status", "?")] = sf_counts.get(c.get("status", "?"), 0) + 1
    for c in lfq:
        lf_counts[c.get("status", "?")] = lf_counts.get(c.get("status", "?"), 0) + 1
    sf_published = sf_counts.get("published", 0) + sf_counts.get("done", 0)
    sf_quarantined = sf_counts.get("quarantined", 0)
    lf_published = lf_counts.get("published", 0) + lf_counts.get("done", 0)
    lf_quarantined = lf_counts.get("quarantined", 0)

    # =================================================================
    # Row builders (iOS grouped-list style)
    # =================================================================
    def row(icon_html, title, subtitle="", trailing="", href=None, chevron=False, multiline=False):
        tag, attrs = ("a", f' href="{esc(href)}" target="_blank" rel="noopener"') if href else ("div", "")
        sub = f'<div class="row-subtitle{" row-subtitle-wrap" if multiline else ""}">{subtitle}</div>' if subtitle else ""
        trail = f'<div class="row-trailing">{trailing}{icon("chevron", 15) if chevron else ""}</div>'
        return (
            f'<{tag} class="ios-row"{attrs}>{icon_html}'
            f'<div class="row-text"><div class="row-title">{title}</div>{sub}</div>'
            f"{trail}</{tag}>"
        )

    def section(title, rows_html, note=""):
        rows_html = rows_html or '<div class="ios-row"><div class="row-text"><div class="row-title muted-text">Nothing here yet.</div></div></div>'
        note_html = f'<div class="ios-footer">{note}</div>' if note else ""
        return (
            f'<div class="ios-section">'
            f'<div class="ios-section-header">{esc(title)}</div>'
            f'<div class="ios-list">{rows_html}</div>'
            f"{note_html}</div>"
        )

    # ---- Agents tab ----
    def agent_row(num, name, md_path, tone):
        role = role_text(md_path)
        return row(icon_bubble(num, tone), esc(name), esc(role), multiline=True)

    gates_row = row(
        icon_bubble(icon("check", 15), "warning", is_svg=True),
        "Gates",
        esc(
            "Every candidate must pass the shared and format-specific gates in "
            "config/gates.json before it can move to ready_to_publish — factual/"
            "controversy screen, platform policy check, basic QA, copyright "
            "mitigation, and audio license check. A failing candidate is "
            "quarantined with a logged reason and the next candidate is "
            "scouted instead; gates are never lowered to hit the publishing "
            "schedule."
        ),
        multiline=True,
    )

    sf_agent_rows = "".join([
        agent_row("1.1", "Trend Scout", "short_form/1.1_trend_scout.md", "accent"),
        agent_row("2.1", "Scriptwriter", "short_form/2.1_scriptwriter.md", "accent"),
        agent_row("3.1", "Producer", "short_form/3.1_producer.md", "accent"),
        gates_row,
        agent_row("4.1", "Publisher", "short_form/4.1_publisher.md", "success"),
    ])

    lf_agent_rows = "".join([
        agent_row("1.2", "Format Scout", "long_form/1.2_format_scout.md", "info"),
        agent_row("2.2", "Image Sourcer", "long_form/2.2_image_sourcer.md", "info"),
        agent_row("3.2", "Animator", "long_form/3.2_animator.md", "info"),
        agent_row("4.2", "Sound Sourcer", "long_form/4.2_sound_sourcer.md", "info"),
        agent_row("5", "Assembler / Looper", "long_form/5_assembler.md", "info"),
        agent_row("6", "Publisher", "long_form/6_publisher.md", "success"),
    ])

    orchestrator_role = role_text("0_orchestrator.md")

    # ---- Overview tab ----
    def stat_card(label, value, tone="neutral", sub=""):
        return f"""<div class="stat-card">
          <div class="stat-icon stat-icon-{tone}">{icon('check' if tone=='success' else ('warn' if tone=='critical' else 'gauge'), 14)}</div>
          <div class="stat-value">{value}</div>
          <div class="stat-label">{esc(label)}</div>
          {f'<div class="stat-sub">{esc(sub)}</div>' if sub else ''}
        </div>"""

    stats_html = "".join([
        stat_card("Published", status_counts.get("done", 0), "success"),
        stat_card("Ready to publish", status_counts.get("ready_to_publish", 0), "info"),
        stat_card("Pending", status_counts.get("pending", 0), "neutral"),
        stat_card("Quarantined", quarantine_count, "critical" if quarantine_count else "neutral"),
    ])

    next_row = ""
    if next_due:
        next_row = section(
            "Next scheduled",
            row(
                icon_bubble(icon("gauge", 15), "accent", is_svg=True),
                esc(next_due.get("candidate_id", "—")),
                f'{esc(fmt_dt(next_due["scheduled_publish_at"]))} · {"Short-form" if next_due.get("format")=="short" else "Long-form"}',
            ),
        )

    blocker_html = ""
    if blockers:
        rows = "".join(
            row(
                icon_bubble(icon("warn", 15), "critical", is_svg=True),
                esc(bid) + " — " + esc(title),
                esc(note),
                multiline=True,
            )
            for bid, title, note in blockers
        )
        blocker_html = section("⚠️ Blocked on publish", rows)

    slot_order = {"09:00": 0, "14:00": 1, "19:00": 2, "20:00": 3}
    week_sections = []
    for entry in days:
        slots = sorted(entry["slots"], key=lambda s: slot_order.get(s.get("local_slot"), 9))
        rows_html = "".join(
            row(
                icon_bubble("S" if s.get("format") == "short" else "L", "accent" if s.get("format") == "short" else "info"),
                esc(s.get("candidate_id") or "—"),
                f'{esc(s.get("local_slot",""))} · {"Short-form" if s.get("format")=="short" else "Long-form"}',
                trailing=pill(s.get("status")),
            )
            for s in slots
        )
        week_sections.append(section(fmt_day(entry["day"]), rows_html))
    week_html = "".join(week_sections) or section("This week", "")

    # ---- Queues tab ----
    def lf_row_html(c):
        return row(
            icon_bubble("L", "info"),
            esc(c.get("title", c["id"])),
            f'{esc(c["id"])} · {esc(c.get("target_length_minutes","—"))} min',
            trailing=pill(c.get("status")),
        )

    def sf_row_html(c):
        return row(
            icon_bubble("S", "accent"),
            esc(c.get("title", c["id"])),
            esc(c["id"]),
            trailing=pill(c.get("status")),
        )

    lf_queue_html = section(f"Long-form ({len(lfq)})", "".join(lf_row_html(c) for c in lfq))
    sf_queue_html = section(f"Short-form ({len(sfq)})", "".join(sf_row_html(c) for c in sfq))

    # ---- Activity tab ----
    def activity_row_html(v):
        return row(
            icon_bubble("S" if v["kind"] == "short" else "L", "accent" if v["kind"] == "short" else "info"),
            esc(v.get("title", "—")),
            esc(fmt_dt(v.get("published_at"))),
            href=v.get("url"),
            chevron=True,
        )

    activity_html = section("Recently published", "".join(activity_row_html(v) for v in activity))

    # =================================================================
    # PWA icon + manifest (best-effort "Add to Home Screen")
    # =================================================================
    icon192_b64 = make_icon_png_b64(192)
    icon180_b64 = make_icon_png_b64(180)

    manifest = {
        "name": f"{handle} Pipeline",
        "short_name": "Pipeline",
        "description": "Status dashboard for the YouTube automation content pipeline.",
        "start_url": ".",
        "display": "standalone",
        "background_color": "#000000",
        "theme_color": "#000000",
        "icons": [
            {"src": f"data:image/png;base64,{icon192_b64}", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
        ],
    }
    manifest_data_uri = "data:application/manifest+json," + json.dumps(manifest).replace("#", "%23")

    pwa_head = f"""<link rel="manifest" href="{manifest_data_uri}" />
<meta name="theme-color" content="#000000" media="(prefers-color-scheme: dark)" />
<meta name="theme-color" content="#f2f2f7" media="(prefers-color-scheme: light)" />
<meta name="mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-capable" content="yes" />
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
<meta name="apple-mobile-web-app-title" content="Pipeline" />
<link rel="apple-touch-icon" href="data:image/png;base64,{icon180_b64}" />
<link rel="icon" href="data:image/png;base64,{icon192_b64}" />"""

    footer_note = (
        f'Read from state/*.json and agents/*.md at generation time · '
        f'image pool clean/unused: {len(clean_unused)}, pending vet: {len(pending_images)}<br/>'
        f'Add to Home Screen from your phone\'s browser to install.'
    )

    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
<title>{esc(handle)} — Pipeline Dashboard</title>

{pwa_head}

<style>
:root {{
  --bg: #000000;
  --surface: #1c1c1e;
  --surface-2: #2c2c2e;
  --border: rgba(255,255,255,0.14);
  --text: #ffffff;
  --text-secondary: rgba(235,235,245,0.6);
  --text-tertiary: rgba(235,235,245,0.35);
  --accent: #cd9a5c;
  --success: #30d158;
  --info: #409cff;
  --warning: #ffd60a;
  --critical: #ff453a;
  --neutral: #8e8e93;
  --bar-bg: rgba(28,28,30,0.78);
  font-variant-numeric: tabular-nums;
}}
:root[data-theme="light"] {{
  --bg: #f2f2f7;
  --surface: #ffffff;
  --surface-2: #e5e5ea;
  --border: rgba(60,60,67,0.16);
  --text: #000000;
  --text-secondary: rgba(60,60,67,0.6);
  --text-tertiary: rgba(60,60,67,0.3);
  --accent: #a9682c;
  --success: #34c759;
  --info: #007aff;
  --warning: #b3811f;
  --critical: #ff3b30;
  --neutral: #8e8e93;
  --bar-bg: rgba(248,248,250,0.78);
}}
@media (prefers-color-scheme: light) {{
  :root:not([data-theme="dark"]) {{
    --bg: #f2f2f7;
    --surface: #ffffff;
    --surface-2: #e5e5ea;
    --border: rgba(60,60,67,0.16);
    --text: #000000;
    --text-secondary: rgba(60,60,67,0.6);
    --text-tertiary: rgba(60,60,67,0.3);
    --accent: #a9682c;
    --success: #34c759;
    --info: #007aff;
    --warning: #b3811f;
    --critical: #ff3b30;
    --neutral: #8e8e93;
    --bar-bg: rgba(248,248,250,0.78);
  }}
}}
* {{ box-sizing: border-box; -webkit-tap-highlight-color: transparent; }}
html {{ -webkit-text-size-adjust: 100%; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, "SF Pro Text", "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
}}
.mono {{ font-family: ui-monospace, "SF Mono", "Cascadia Code", "Roboto Mono", monospace; }}
.muted-text {{ color: var(--text-tertiary); }}

/* ---- Nav bar (per tab, sticky, iOS large title) ---- */
.navbar {{
  position: sticky;
  top: 0;
  z-index: 40;
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  background: var(--bar-bg);
  border-bottom: 0.5px solid var(--border);
  padding-top: env(safe-area-inset-top);
}}
.navbar-compact {{
  height: 44px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 17px;
  font-weight: 600;
  padding: 0 16px;
}}
.large-title-block {{ padding: 4px 16px 12px; }}
.large-title {{
  font-size: 34px;
  font-weight: 700;
  letter-spacing: -0.021em;
  margin: 0;
  text-wrap: balance;
}}
.large-title-sub {{
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 2px;
}}

/* ---- Page / tab content ---- */
.page-wrap {{ max-width: 640px; margin: 0 auto; }}
.tab-page {{ display: none; padding-bottom: calc(100px + env(safe-area-inset-bottom)); }}
.tab-page.active {{ display: block; animation: iosIn 0.24s cubic-bezier(0.22,1,0.36,1); }}
@keyframes iosIn {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: none; }} }}
@media (prefers-reduced-motion: reduce) {{
  .tab-page.active {{ animation: none; }}
}}

/* ---- Stat widgets (Overview) ---- */
.stats-grid {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  padding: 0 16px 8px;
}}
.stat-card {{
  background: var(--surface);
  border-radius: 16px;
  padding: 14px 14px 12px;
  position: relative;
}}
.stat-icon {{
  width: 26px; height: 26px;
  border-radius: 8px;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  margin-bottom: 20px;
}}
.stat-icon svg {{ width: 14px; height: 14px; }}
.stat-icon-success {{ background: var(--success); }}
.stat-icon-info {{ background: var(--info); }}
.stat-icon-neutral {{ background: var(--neutral); }}
.stat-icon-critical {{ background: var(--critical); }}
.stat-value {{ font-size: 28px; font-weight: 700; letter-spacing: -0.01em; font-family: ui-monospace, "SF Mono", monospace; }}
.stat-label {{ font-size: 13px; color: var(--text-secondary); margin-top: 1px; }}
.stat-sub {{ font-size: 11px; color: var(--text-tertiary); margin-top: 3px; font-family: ui-monospace, monospace; }}

/* ---- Grouped inset list (iOS Settings-style) ---- */
.ios-section {{ margin: 20px 0 0; }}
.ios-section:first-child {{ margin-top: 4px; }}
.ios-section-header {{
  font-size: 13px;
  font-weight: 400;
  text-transform: uppercase;
  letter-spacing: 0.02em;
  color: var(--text-secondary);
  padding: 0 30px 6px;
}}
.ios-list {{
  background: var(--surface);
  border-radius: 14px;
  margin: 0 16px;
  overflow: hidden;
}}
.ios-footer {{
  font-size: 13px;
  color: var(--text-secondary);
  padding: 8px 30px 0;
  line-height: 1.4;
}}
.ios-row {{
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-height: 44px;
  padding: 10px 16px;
  border-bottom: 0.5px solid var(--border);
  text-decoration: none;
  color: inherit;
}}
.ios-row:last-child {{ border-bottom: none; }}
.ios-row:active {{ background: var(--surface-2); }}
.row-icon {{
  width: 29px; height: 29px;
  border-radius: 8px;
  flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  margin-top: 1px;
}}
.row-icon svg {{ width: 15px; height: 15px; }}
.row-icon-accent {{ background: var(--accent); }}
.row-icon-info {{ background: var(--info); }}
.row-icon-success {{ background: var(--success); }}
.row-icon-warning {{ background: var(--warning); color: #1c1c1e; }}
.row-icon-critical {{ background: var(--critical); }}
.row-text {{ flex: 1; min-width: 0; padding-top: 3px; }}
.row-title {{
  font-size: 16px;
  line-height: 1.3;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.row-subtitle {{
  font-size: 13px;
  color: var(--text-secondary);
  margin-top: 1px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.row-subtitle-wrap {{
  white-space: normal;
  line-height: 1.4;
  margin-top: 3px;
}}
.row-trailing {{
  display: flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
  color: var(--text-tertiary);
  padding-top: 3px;
}}

.pill {{
  display: inline-block;
  font-size: 11px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 999px;
  letter-spacing: 0.01em;
  white-space: nowrap;
}}
.pill-success {{ background: color-mix(in srgb, var(--success) 20%, transparent); color: var(--success); }}
.pill-info {{ background: color-mix(in srgb, var(--info) 20%, transparent); color: var(--info); }}
.pill-critical {{ background: color-mix(in srgb, var(--critical) 20%, transparent); color: var(--critical); }}
.pill-neutral {{ background: color-mix(in srgb, var(--neutral) 24%, transparent); color: var(--text-secondary); }}
.pill-warning {{ background: color-mix(in srgb, var(--warning) 24%, transparent); color: var(--warning); }}

/* ---- Orchestrator banner ---- */
.banner {{
  margin: 4px 16px 4px;
  background: var(--surface);
  border-radius: 16px;
  padding: 14px 16px 16px;
}}
.banner-head {{ display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }}
.banner-head .row-icon {{ margin-top: 0; }}
.banner-title {{ font-size: 16px; font-weight: 600; }}
.banner p {{ font-size: 13.5px; color: var(--text-secondary); line-height: 1.5; margin: 0; }}

/* ---- Segmented control (Queues tab) ---- */
.segmented {{
  display: flex;
  background: var(--surface-2);
  border-radius: 9px;
  padding: 2px;
  margin: 4px 16px 4px;
  gap: 2px;
}}
.segmented button {{
  flex: 1;
  border: none;
  background: transparent;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 6px 0;
  border-radius: 7px;
  cursor: pointer;
}}
.segmented button.active {{
  background: var(--surface);
  color: var(--text);
  box-shadow: 0 1px 2px rgba(0,0,0,0.3);
}}
.queue-panel {{ display: none; }}
.queue-panel.active {{ display: block; }}

/* ---- Bottom tab bar ---- */
.tabbar {{
  position: fixed;
  left: 0; right: 0; bottom: 0;
  z-index: 50;
  display: flex;
  backdrop-filter: saturate(180%) blur(20px);
  -webkit-backdrop-filter: saturate(180%) blur(20px);
  background: var(--bar-bg);
  border-top: 0.5px solid var(--border);
  padding-bottom: env(safe-area-inset-bottom);
}}
.tab-btn {{
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  padding: 7px 0 6px;
  background: none;
  border: none;
  color: var(--text-tertiary);
  font: inherit;
  font-size: 10px;
  font-weight: 500;
  cursor: pointer;
}}
.tab-btn svg {{ width: 25px; height: 25px; }}
.tab-btn.active {{ color: var(--accent); }}
.tab-btn:active {{ opacity: 0.5; }}

@media (min-width: 700px) {{
  .stats-grid {{ grid-template-columns: repeat(4, 1fr); }}
}}
</style>
</head>
<body>

<nav class="navbar">
  <div class="navbar-compact" id="navTitle">Overview</div>
</nav>

<main class="page-wrap">

  <section class="tab-page active" id="tab-overview">
    <div class="large-title-block">
      <h1 class="large-title">Overview</h1>
      <div class="large-title-sub">{esc(handle)} · generated {esc(generated_at)}</div>
    </div>
    <div class="stats-grid">{stats_html}</div>
    {blocker_html}
    {next_row}
    {week_html}
  </section>

  <section class="tab-page" id="tab-agents">
    <div class="large-title-block">
      <h1 class="large-title">Agents</h1>
      <div class="large-title-sub">Live from agents/*.md</div>
    </div>
    <div class="banner">
      <div class="banner-head">{icon_bubble(icon('gauge', 15), 'accent', is_svg=True)}<div class="banner-title">Agent 0 — Orchestrator</div></div>
      <p>{esc(orchestrator_role)}</p>
    </div>
    {section(f"Short-form · {len(sfq)} total, {sf_published} published, {sf_quarantined} quarantined", sf_agent_rows)}
    {section(f"Long-form · {len(lfq)} total, {lf_published} published, {lf_quarantined} quarantined", lf_agent_rows)}
  </section>

  <section class="tab-page" id="tab-queues">
    <div class="large-title-block">
      <h1 class="large-title">Queues</h1>
      <div class="large-title-sub">{len(lfq) + len(sfq)} candidates total</div>
    </div>
    <div class="segmented">
      <button class="active" data-queue="long">Long-form</button>
      <button data-queue="short">Short-form</button>
    </div>
    <div class="queue-panel active" id="queue-long">{lf_queue_html}</div>
    <div class="queue-panel" id="queue-short">{sf_queue_html}</div>
  </section>

  <section class="tab-page" id="tab-activity">
    <div class="large-title-block">
      <h1 class="large-title">Activity</h1>
      <div class="large-title-sub">Recently published</div>
    </div>
    {activity_html}
    <div class="ios-footer" style="margin:16px 16px 0;">{footer_note}</div>
  </section>

</main>

<nav class="tabbar">
  <button class="tab-btn active" data-tab="overview" data-title="Overview">{icon('gauge')}<span>Overview</span></button>
  <button class="tab-btn" data-tab="agents" data-title="Agents">{icon('agents')}<span>Agents</span></button>
  <button class="tab-btn" data-tab="queues" data-title="Queues">{icon('queues')}<span>Queues</span></button>
  <button class="tab-btn" data-tab="activity" data-title="Activity">{icon('activity')}<span>Activity</span></button>
</nav>

<script>
(function() {{
  var tabBtns = document.querySelectorAll('.tab-btn');
  var navTitle = document.getElementById('navTitle');
  tabBtns.forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      tabBtns.forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      document.querySelectorAll('.tab-page').forEach(function(p) {{ p.classList.remove('active'); }});
      var page = document.getElementById('tab-' + btn.dataset.tab);
      if (page) page.classList.add('active');
      navTitle.textContent = btn.dataset.title;
      var main = document.querySelector('main');
      if (main) main.scrollTop = 0;
      window.scrollTo(0, 0);
    }});
  }});
  var segBtns = document.querySelectorAll('.segmented button');
  segBtns.forEach(function(btn) {{
    btn.addEventListener('click', function() {{
      segBtns.forEach(function(b) {{ b.classList.remove('active'); }});
      btn.classList.add('active');
      document.querySelectorAll('.queue-panel').forEach(function(p) {{ p.classList.remove('active'); }});
      var panel = document.getElementById('queue-' + btn.dataset.queue);
      if (panel) panel.classList.add('active');
    }});
  }});
}})();
</script>
</body>
</html>
"""

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, "index.html")
    with open(out_path, "w") as f:
        f.write(html)
    print("wrote", out_path, f"({len(html)} bytes)")


if __name__ == "__main__":
    main()
