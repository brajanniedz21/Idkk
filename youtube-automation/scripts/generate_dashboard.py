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
        "chart": '<path d="M5 19V10" stroke-linecap="round"/><path d="M12 19V5" stroke-linecap="round"/><path d="M19 19v-6" stroke-linecap="round"/>',
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
    video_analytics = load("video_analytics.json", {"videos": [], "has_analytics_scope": False, "pulled_at": None})

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

    def chart_card(title, body_html, subtitle=""):
        sub_html = f'<div class="chart-card-sub">{esc(subtitle)}</div>' if subtitle else ""
        return (
            f'<div class="ios-section"><div class="ios-section-header">{esc(title)}</div>'
            f'<div class="chart-card">{sub_html}{body_html}</div></div>'
        )

    def bar_chart(items, color_var, unit=""):
        """items: list of (label, value, href|None) or (label, value, href, color).
        Horizontal bars sharing one scale (common max across all items) —
        pass a per-item color as a 4th tuple element for a small (<=3)
        categorical comparison; omit it for a single-hue magnitude chart.
        Value sits at the tip — see dataviz skill marks-and-anatomy."""
        items = [it for it in items if it]
        if not items:
            return '<div class="chart-empty">No data yet.</div>'
        # Headroom so the longest bar's value label has room to sit after
        # it in the same row instead of overflowing the container — a
        # 100%-width fill leaves zero space for the label in a nowrap flex
        # row, which is exactly the bug this constant fixes.
        max_val = (max((it[1] for it in items), default=0) or 1) * 1.22
        rows = []
        for it in items:
            label, value, href = it[0], it[1], it[2]
            color = it[3] if len(it) > 3 else color_var
            pct = max(2, round((value / max_val) * 100, 1))
            val_str = f"{value:,}{unit}"
            label_html = esc(label)
            if href:
                label_html = f'<a href="{esc(href)}" target="_blank" rel="noopener">{label_html}</a>'
            rows.append(
                f'<div class="bar-row"><div class="bar-label">{label_html}</div>'
                f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%;background:{color}"></div>'
                f'<span class="bar-value">{val_str}</span></div></div>'
            )
        return "".join(rows)

    def trend_chart(daily_series, color_var="var(--accent)", metric_key="views", metric_label="views"):
        """Line + area chart over channel daily totals. Real historical
        series from the Analytics API (dimensions=day) — no local snapshot
        history needed. Shows an honest empty state rather than a
        misleading flat-zero line when YouTube's processing hasn't caught
        up yet (routine on a very new channel)."""
        points = [d for d in daily_series if d.get(metric_key) is not None]
        total = sum(d.get(metric_key, 0) for d in points)
        if not points or total == 0:
            return (
                '<div class="chart-empty">'
                "Waiting on YouTube's analytics processing to catch up — this fills in "
                "automatically once it does (routine lag on a new channel, not an error)."
                "</div>"
            )
        W, H, PAD_L, PAD_B, PAD_T = 600, 160, 44, 22, 14
        vals = [d.get(metric_key, 0) for d in points]
        max_v = max(vals) or 1
        n = len(points)
        plot_w = W - PAD_L - 8
        plot_h = H - PAD_B - PAD_T

        def xy(i, v):
            x = PAD_L + (plot_w * (i / (n - 1)) if n > 1 else plot_w / 2)
            y = PAD_T + plot_h - (plot_h * (v / max_v))
            return x, y

        coords = [xy(i, v) for i, v in enumerate(vals)]
        line_path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in coords)
        area_path = line_path + f" L {coords[-1][0]:.1f} {PAD_T+plot_h:.1f} L {coords[0][0]:.1f} {PAD_T+plot_h:.1f} Z"
        last_x, last_y = coords[-1]
        last_label = f"{vals[-1]:,} {metric_label}"

        gridlines = (
            f'<line x1="{PAD_L}" y1="{PAD_T+plot_h:.1f}" x2="{W-8}" y2="{PAD_T+plot_h:.1f}" class="chart-grid"/>'
            f'<text x="4" y="{PAD_T+plot_h+4:.1f}" class="chart-axis-label">0</text>'
            f'<line x1="{PAD_L}" y1="{PAD_T:.1f}" x2="{W-8}" y2="{PAD_T:.1f}" class="chart-grid"/>'
            f'<text x="4" y="{PAD_T+4:.1f}" class="chart-axis-label">{max_v:,}</text>'
        )
        first_date = points[0]["date"][5:]
        last_date = points[-1]["date"][5:]
        return f"""<svg viewBox="0 0 {W} {H}" class="trend-svg" preserveAspectRatio="none" role="img" aria-label="{esc(metric_label)} trend">
          {gridlines}
          <path d="{area_path}" class="chart-area" fill="{color_var}"/>
          <path d="{line_path}" class="chart-line" stroke="{color_var}" fill="none"/>
          <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="{color_var}" class="chart-dot"/>
          <text x="{min(last_x, W-90):.1f}" y="{max(last_y-10, 12):.1f}" class="chart-end-label">{esc(last_label)}</text>
          <text x="{PAD_L}" y="{H-4}" class="chart-axis-label">{esc(first_date)}</text>
          <text x="{W-8}" y="{H-4}" class="chart-axis-label" text-anchor="end">{esc(last_date)}</text>
        </svg>"""

    def retention_chart(points, color_var="var(--info)"):
        """Audience retention curve: x = % of video elapsed, y = % of
        audience still watching. Real per-video data from the Analytics
        API (elapsedVideoTimeRatio / audienceWatchRatio), no fabrication —
        empty state when a video doesn't have retention data yet."""
        if not points:
            return (
                '<div class="chart-empty">'
                "No retention data yet — needs a video with enough views for YouTube to "
                "compute a curve, and the same processing lag as the other Analytics metrics."
                "</div>"
            )
        W, H, PAD_L, PAD_B, PAD_T = 600, 160, 30, 22, 14
        plot_w = W - PAD_L - 8
        plot_h = H - PAD_B - PAD_T
        pts = sorted(points, key=lambda p: p["elapsed"])
        n = len(pts)

        def xy(i, p):
            x = PAD_L + plot_w * (p["elapsed"])
            y = PAD_T + plot_h - (plot_h * min(1.0, p["ratio"]))
            return x, y

        coords = [xy(i, p) for i, p in enumerate(pts)]
        line_path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in coords)
        area_path = line_path + f" L {coords[-1][0]:.1f} {PAD_T+plot_h:.1f} L {coords[0][0]:.1f} {PAD_T+plot_h:.1f} Z"
        last_x, last_y = coords[-1]
        last_pct = round(pts[-1]["ratio"] * 100)
        gridlines = (
            f'<line x1="{PAD_L}" y1="{PAD_T+plot_h:.1f}" x2="{W-8}" y2="{PAD_T+plot_h:.1f}" class="chart-grid"/>'
            f'<text x="2" y="{PAD_T+plot_h+4:.1f}" class="chart-axis-label">0%</text>'
            f'<line x1="{PAD_L}" y1="{PAD_T:.1f}" x2="{W-8}" y2="{PAD_T:.1f}" class="chart-grid"/>'
            f'<text x="2" y="{PAD_T+4:.1f}" class="chart-axis-label">100%</text>'
        )
        return f"""<svg viewBox="0 0 {W} {H}" class="trend-svg" preserveAspectRatio="none" role="img" aria-label="audience retention">
          {gridlines}
          <path d="{area_path}" class="chart-area" fill="{color_var}"/>
          <path d="{line_path}" class="chart-line" stroke="{color_var}" fill="none"/>
          <circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="4" fill="{color_var}" class="chart-dot"/>
          <text x="{min(last_x, W-70):.1f}" y="{max(last_y-10, 12):.1f}" class="chart-end-label">{last_pct}%</text>
          <text x="{PAD_L}" y="{H-4}" class="chart-axis-label">Start</text>
          <text x="{W-8}" y="{H-4}" class="chart-axis-label" text-anchor="end">End</text>
        </svg>"""

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

    # ---- Analytics tab ----
    analytics_videos = sorted(
        video_analytics.get("videos", []),
        key=lambda v: v.get("views") or 0,
        reverse=True,
    )
    has_analytics_scope = video_analytics.get("has_analytics_scope", False)
    total_views = sum(v.get("views") or 0 for v in analytics_videos)
    total_likes = sum(v.get("likes") or 0 for v in analytics_videos)
    total_watched_min = sum(v.get("estimated_minutes_watched") or 0 for v in analytics_videos)

    analytics_stats_html = "".join([
        stat_card("Total views", total_views, "success"),
        stat_card("Total likes", total_likes, "info"),
        stat_card("Minutes watched", total_watched_min, "neutral", sub="0 while data catches up" if not total_watched_min else ""),
        stat_card("Videos tracked", len(analytics_videos), "neutral"),
    ])

    def analytics_row_html(v):
        views = v.get("views")
        views_str = f"{views:,}" if views is not None else "—"
        watched = v.get("estimated_minutes_watched")
        sub_parts = [f'{esc(v.get("likes") or 0)} likes']
        if watched:
            sub_parts.append(f"{esc(watched)} min watched")
        return row(
            icon_bubble("S" if v["format"] == "short" else "L", "accent" if v["format"] == "short" else "info"),
            esc(v.get("title", "—")),
            " · ".join(sub_parts),
            trailing=f'<span class="mono">{views_str}</span>&nbsp;views',
            href=v.get("url"),
            chevron=True,
        )

    if not analytics_videos:
        analytics_list_html = section("Per-video stats", "")
    else:
        analytics_list_html = section(f"Per-video stats ({len(analytics_videos)})", "".join(analytics_row_html(v) for v in analytics_videos))

    # Views by video — horizontal bar chart, top 10, one hue (magnitude comparison)
    views_bar_items = [
        (v.get("title", "—")[:36], v.get("views") or 0, v.get("url"))
        for v in analytics_videos[:10]
    ]
    views_bar_html = chart_card(
        "Views by video",
        bar_chart(views_bar_items, "var(--accent)"),
        subtitle="Top 10 of " + str(len(analytics_videos)) if len(analytics_videos) > 10 else "",
    )

    # Short-form vs long-form — 2-category comparison, direct-labeled
    sf_views_total = sum(v.get("views") or 0 for v in analytics_videos if v["format"] == "short")
    lf_views_total = sum(v.get("views") or 0 for v in analytics_videos if v["format"] == "long")
    format_bar_html = chart_card(
        "Views by format",
        bar_chart(
            [
                ("Short-form", sf_views_total, None, "var(--accent)"),
                ("Long-form", lf_views_total, None, "var(--info)"),
            ],
            "var(--accent)",
        ),
    )

    # Views over time — real day-by-day channel trend
    trend_html = chart_card(
        "Views over time",
        trend_chart(video_analytics.get("daily_series", []), "var(--accent)", "views", "views"),
    )

    # Traffic sources — where views actually come from
    TRAFFIC_SOURCE_LABELS = {
        "YT_SEARCH": "YouTube search",
        "SUGGESTED_VIDEO": "Suggested videos",
        "BROWSE": "Browse / Home",
        "EXTERNAL": "External sites",
        "NOTIFICATION": "Notifications",
        "PLAYLIST": "Playlists",
        "SHORTS": "Shorts feed",
        "CHANNEL": "Channel page",
        "NO_LINK_OTHER": "Direct / unlinked",
        "SUBSCRIBER": "Subscription feed",
    }
    traffic_items = [
        (TRAFFIC_SOURCE_LABELS.get(t.get("source"), t.get("source")), t.get("views") or 0, None)
        for t in (video_analytics.get("traffic_sources") or [])
    ]
    traffic_html = chart_card("Traffic sources", bar_chart(traffic_items, "var(--info)"))

    # Audience retention curve — for the single most-viewed video
    retention_curve = video_analytics.get("retention_curve")
    retention_video = video_analytics.get("retention_video")
    retention_html = chart_card(
        "Audience retention",
        retention_chart(retention_curve),
        subtitle=esc(retention_video["title"]) if retention_video else "",
    )

    subs_gained = video_analytics.get("subscribers_gained")
    subs_lost = video_analytics.get("subscribers_lost")
    subs_html = ""
    if subs_gained is not None:
        subs_net = subs_gained - subs_lost
        subs_html = chart_card(
            "Subscribers",
            bar_chart(
                [("Gained", subs_gained, None, "var(--success)"), ("Lost", subs_lost, None, "var(--critical)")],
                "var(--success)",
            ),
            subtitle=f"Net {'+' if subs_net >= 0 else ''}{subs_net}",
        )

    analytics_note = (
        video_analytics.get("analytics_data_note")
        or (
            "Views/likes/comments are near-real-time via the YouTube Data API. Watch time and average "
            "view duration need the YouTube Analytics API (yt-analytics.readonly scope) — "
            + ("authorized, but YouTube's analytics processing pipeline lags behind the public view counter (often a day or two on a new channel), so those fields read 0/— until it catches up." if has_analytics_scope else "not currently usable — see the note below.")
        )
    )
    ctr_note = video_analytics.get("ctr_impressions_note", "")
    analytics_pulled_note = f'Pulled {esc(fmt_dt(video_analytics.get("pulled_at")))}' if video_analytics.get("pulled_at") else "Not pulled yet"

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

/* ---- Charts (Analytics tab) ---- */
.chart-card {{
  background: var(--surface);
  border-radius: 14px;
  margin: 0 16px;
  padding: 14px 8px 10px;
}}
.chart-card-sub {{
  font-size: 12px;
  color: var(--text-tertiary);
  padding: 0 12px 8px;
}}
.chart-empty {{
  font-size: 13px;
  color: var(--text-secondary);
  padding: 20px 16px;
  line-height: 1.5;
  text-align: center;
}}
.bar-row {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 12px;
}}
.bar-label {{
  width: 118px;
  flex-shrink: 0;
  font-size: 12.5px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}}
.bar-label a {{ color: inherit; text-decoration: none; }}
.bar-track {{
  flex: 1;
  display: flex;
  align-items: center;
  height: 20px;
  min-width: 0;
  max-width: 100%;
}}
.bar-fill {{
  height: 20px;
  min-width: 3px;
  max-width: 78%;
  border-radius: 0 4px 4px 0;
  flex-shrink: 0;
  transition: width 0.4s cubic-bezier(0.22,1,0.36,1);
}}
.bar-value {{
  margin-left: 8px;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--text);
  font-family: ui-monospace, "SF Mono", monospace;
  white-space: nowrap;
}}
.trend-svg {{
  width: 100%;
  height: 150px;
  display: block;
  overflow: hidden;
}}
.chart-grid {{ stroke: var(--border); stroke-width: 1; }}
.chart-axis-label {{
  font-size: 9px;
  fill: var(--text-tertiary);
  font-family: ui-monospace, monospace;
}}
.chart-area {{ opacity: 0.12; }}
.chart-line {{ stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }}
.chart-end-label {{
  font-size: 10.5px;
  font-weight: 600;
  fill: var(--text);
  font-family: ui-monospace, monospace;
}}

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

  <section class="tab-page" id="tab-analytics">
    <div class="large-title-block">
      <h1 class="large-title">Analytics</h1>
      <div class="large-title-sub">{esc(analytics_pulled_note)}</div>
    </div>
    <div class="stats-grid">{analytics_stats_html}</div>
    {trend_html}
    {retention_html}
    {traffic_html}
    {subs_html}
    {views_bar_html}
    {format_bar_html}
    {analytics_list_html}
    <div class="ios-footer" style="margin:16px 16px 0;">{esc(analytics_note)}</div>
    <div class="ios-footer" style="margin:4px 16px 0;">{esc(ctr_note)}</div>
  </section>

</main>

<nav class="tabbar">
  <button class="tab-btn active" data-tab="overview" data-title="Overview">{icon('gauge')}<span>Overview</span></button>
  <button class="tab-btn" data-tab="agents" data-title="Agents">{icon('agents')}<span>Agents</span></button>
  <button class="tab-btn" data-tab="queues" data-title="Queues">{icon('queues')}<span>Queues</span></button>
  <button class="tab-btn" data-tab="analytics" data-title="Analytics">{icon('chart')}<span>Analytics</span></button>
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
