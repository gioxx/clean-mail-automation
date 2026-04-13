#!/usr/bin/env python3
"""HTTP status page for clean-mail-automation.

Always started by entrypoint.sh inside the Docker container.
Listens on WEB_PORT (default 8080). Not started by clean_email.py directly.
Reads configuration from env vars and last-run state from STATE_FILE.
"""

import datetime
import http.server
import json
import os
import socketserver
import subprocess
import sys
from html import escape

STATE_FILE = "/tmp/clean_mail_last_run.json"
DEFAULT_MAILBOX = "INBOX"
APP_VERSION = "0.5.1"


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _get_mailbox_configs():
    """Return list of mailbox dicts (passwords redacted) from env vars."""
    raw = os.getenv("MAILBOX_CONFIGS")
    if raw:
        try:
            configs = json.loads(raw)
            if isinstance(configs, list) and configs:
                result = []
                for cfg in configs:
                    if not isinstance(cfg, dict):
                        continue
                    email_user = cfg.get("email_user") or cfg.get("EMAIL_USER") or ""
                    result.append({
                        "email_address": cfg.get("email_address") or cfg.get("EMAIL_ADDRESS") or email_user,
                        "imap_server": cfg.get("imap_server") or cfg.get("IMAP_SERVER") or "",
                        "imap_port": cfg.get("imap_port") or cfg.get("IMAP_PORT") or 993,
                        "mailbox": cfg.get("mailbox") or cfg.get("MAILBOX") or DEFAULT_MAILBOX,
                        "clean_days": cfg.get("clean_days") or cfg.get("CLEAN_DAYS") or os.getenv("CLEAN_DAYS", 10),
                    })
                if result:
                    return result
        except (json.JSONDecodeError, Exception):
            pass

    email_user = os.getenv("EMAIL_USER", "")
    return [{
        "email_address": os.getenv("EMAIL_ADDRESS") or email_user,
        "imap_server": os.getenv("IMAP_SERVER", ""),
        "imap_port": os.getenv("IMAP_PORT", 993),
        "mailbox": os.getenv("MAILBOX", DEFAULT_MAILBOX),
        "clean_days": os.getenv("CLEAN_DAYS", 10),
    }]


def _get_schedule():
    """Return (cron_expr, human_readable) from SCHEDULE_* env vars."""
    min_ = os.getenv("SCHEDULE_MIN", "0")
    hour_ = os.getenv("SCHEDULE_HOUR", "0")
    day_ = os.getenv("SCHEDULE_DAY", "0")

    cron_expr = f"{min_} {hour_} * * {day_}"

    day_names = {
        "0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
        "4": "Thursday", "5": "Friday", "6": "Saturday", "*": "every day",
    }

    try:
        h, m = int(hour_), int(min_)
        time_str = f"{h:02d}:{m:02d}"
        day_label = day_names.get(day_, f"day {day_}")
        if day_ == "*":
            description = f"Every day at {time_str}"
        else:
            description = f"Every {day_label} at {time_str}"
    except ValueError:
        description = cron_expr

    return cron_expr, description


def _telegram_status():
    """Return (enabled: bool, detail: str, mode: str, only_if_deleted: bool)."""
    gate = os.getenv("SEND_TELEGRAM_NOTIFICATIONS", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    token = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    chat_id = bool(os.getenv("CLEAN_EMAIL_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID"))
    mode = os.getenv("TELEGRAM_NOTIFY_MODE", "always").strip().lower()
    only_if_deleted = os.getenv("TELEGRAM_NOTIFY_ONLY_IF_DELETED", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }

    if not gate:
        return False, "disabled via SEND_TELEGRAM_NOTIFICATIONS", mode, only_if_deleted
    if not token:
        return False, "TELEGRAM_BOT_TOKEN not set", mode, only_if_deleted
    if not chat_id:
        return False, "TELEGRAM_CHAT_ID not set", mode, only_if_deleted
    return True, "configured", mode, only_if_deleted


def _get_last_run():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
:root {
    --bg: #0f172a;
    --surface: #1e293b;
    --surface2: #162032;
    --border: #334155;
    --text: #e2e8f0;
    --muted: #94a3b8;
    --accent: #3b82f6;
    --accent-dim: #1d4ed822;
    --ok: #22c55e;
    --ok-dim: #14532d33;
    --ok-border: #166534;
    --err: #f87171;
    --err-dim: #7f1d1d33;
    --err-border: #991b1b;
    --warn: #fbbf24;
    --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    --mono: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
    --radius: 0.75rem;
}
body {
    background: var(--bg);
    color: var(--text);
    font-family: var(--font);
    font-size: 0.9375rem;
    line-height: 1.6;
    min-height: 100vh;
}
a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }

/* ---- Header ---- */
header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 1rem 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    flex-wrap: wrap;
}
.logo { display: flex; align-items: center; gap: 0.6rem; }
.logo svg { color: var(--accent); flex-shrink: 0; }
.logo h1 { font-size: 1.1rem; font-weight: 600; letter-spacing: -0.01em; }
.logo h1 em { font-style: normal; color: var(--accent); }
.meta { font-size: 0.78rem; color: var(--muted); text-align: right; line-height: 1.5; }

/* ---- Main layout ---- */
main { max-width: 1100px; margin: 0 auto; padding: 2rem 1.5rem; display: grid; gap: 1.25rem; }

/* ---- Cards ---- */
.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 1.5rem;
}
.card-title {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    font-weight: 600;
    margin-bottom: 1rem;
}
.grid-2 { display: grid; grid-template-columns: 35fr 65fr; gap: 1.25rem; }
.grid-2 > * { min-width: 0; }
main > * { min-width: 0; }
@media (max-width: 720px) { .grid-2 { grid-template-columns: 1fr; } }

/* ---- Mobile ---- */
@media (max-width: 640px) {
    header { padding: 0.75rem 1rem; }
    .meta { text-align: left; }
    main { padding: 1rem 0.75rem; }
    .mini-grid { grid-template-columns: 1fr; }
    .mini-box { grid-column: 1 / -1 !important; }
    .mini-box-split { flex-wrap: wrap; }
    .mini-actions { width: 100%; flex-direction: row; justify-content: flex-start; }
    table { min-width: unset; font-size: 0.78rem; }
    thead th, tbody td { padding: 0.45rem 0.5rem; }
    .guide-body table { min-width: 420px; }
    .hide-mobile { display: none; }
    #totop { width: 2.1rem; height: 2.1rem; font-size: 0.95rem; bottom: 1rem; right: 1rem; }
}

/* ---- Stat rows ---- */
.stat-row { display: flex; flex-direction: column; gap: 0.2rem; margin-bottom: 0.9rem; }
.stat-row:last-child { margin-bottom: 0; }
.stat-label { font-size: 0.75rem; color: var(--muted); }
.stat-value { font-size: 0.95rem; font-weight: 500; display: flex; align-items: center; gap: 0.4rem; }

/* ---- Badges ---- */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 0.1rem 0.55rem;
    border-radius: 9999px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    line-height: 1.6;
}
.badge-ok    { background: var(--ok-dim);  color: var(--ok);   border: 1px solid var(--ok-border); }
.badge-err   { background: var(--err-dim); color: var(--err);  border: 1px solid var(--err-border); }
.badge-muted { background: var(--surface2); color: var(--muted); border: 1px solid var(--border); }
.badge-count { background: var(--accent-dim); color: var(--accent); border: 1px solid var(--accent); }

/* ---- Card header with badge ---- */
.card-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 1rem;
}
.card-header .card-title { margin-bottom: 0; }

/* ---- Mini-boxes inside cards ---- */
.mini-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.65rem;
}
.mini-box {
    background: var(--surface2);
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    padding: 0.6rem 0.8rem;
    display: flex;
    flex-direction: column;
    gap: 0.28rem;
}
.mini-box .stat-label { font-size: 0.72rem; color: var(--muted); }
.mini-box .stat-value { font-size: 0.9rem; font-weight: 500; display: flex; align-items: center; gap: 0.4rem; }
.mini-box .stat-sub  { font-size: 0.76rem; color: var(--muted); }
.mini-box-split { display: flex; gap: 0.5rem; align-items: stretch; }
.mini-box-split .mini-box-main { flex: 1; display: flex; flex-direction: column; gap: 0.28rem; }
.mini-actions { display: flex; flex-direction: column; gap: 0.35rem; justify-content: center; align-self: center; }

/* ---- Action buttons ---- */
.btn-action {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.4rem 0.9rem;
    border-radius: 9999px;
    border: 1px solid var(--border);
    background: var(--surface);
    color: var(--muted);
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
    text-decoration: none;
    transition: border-color 0.15s, color 0.15s, background 0.15s;
    white-space: nowrap;
}
.btn-action:hover { border-color: var(--accent); color: var(--text); background: var(--accent-dim); text-decoration: none; }
.btn-action svg { flex-shrink: 0; }

/* ---- Back-to-top button ---- */
#totop {
    position: fixed;
    bottom: 1.75rem;
    right: 1.75rem;
    width: 2.6rem;
    height: 2.6rem;
    border-radius: 50%;
    background: var(--accent);
    color: #fff;
    border: none;
    cursor: pointer;
    font-size: 1.2rem;
    display: none;
    align-items: center;
    justify-content: center;
    box-shadow: 0 4px 14px rgba(0,0,0,0.45);
    transition: background 0.2s, transform 0.15s;
    z-index: 999;
    line-height: 1;
}
#totop:hover { background: #2563eb; transform: translateY(-2px); }

/* ---- Code ---- */
code {
    background: var(--surface2);
    border: 1px solid var(--border);
    padding: 0.1rem 0.45rem;
    border-radius: 0.3rem;
    font-family: var(--mono);
    font-size: 0.8rem;
    color: var(--accent);
}

/* ---- Table ---- */
.table-wrap { overflow-x: auto; margin: -0.25rem; }
table { width: 100%; border-collapse: collapse; font-size: 0.85rem; min-width: 480px; }
thead th {
    text-align: left;
    padding: 0.5rem 0.85rem;
    border-bottom: 1px solid var(--border);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--muted);
    font-weight: 600;
    white-space: nowrap;
}
tbody td { padding: 0.65rem 0.85rem; border-bottom: 1px solid var(--border); vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
tbody tr:hover td { background: var(--surface2); }
.cell-err { color: var(--err); font-size: 0.8rem; font-family: var(--mono); }
.cell-muted { color: var(--muted); }

/* ---- Empty state ---- */
.empty { color: var(--muted); font-size: 0.875rem; padding: 0.5rem 0; }

/* ---- Dot indicator ---- */
.dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
}
.dot-ok  { background: var(--ok); box-shadow: 0 0 6px var(--ok); }
.dot-err { background: var(--err); box-shadow: 0 0 6px var(--err); }
.dot-muted { background: var(--muted); }

/* ---- Collapsible guide ---- */
details {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius);
}
summary {
    padding: 1rem 1.5rem;
    cursor: pointer;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    font-weight: 600;
    user-select: none;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}
summary::before {
    content: '▶';
    font-size: 0.6rem;
    transition: transform 0.15s ease;
    display: inline-block;
}
details[open] summary::before { transform: rotate(90deg); }
details[open] summary { border-bottom: 1px solid var(--border); }
.guide-body { padding: 1.5rem; overflow-x: auto; }
.guide-body table { min-width: 560px; }
.guide-body thead th { white-space: nowrap; }
.guide-body td:first-child { font-family: var(--mono); font-size: 0.78rem; color: var(--accent); white-space: nowrap; }
.guide-body td:nth-child(2) { font-family: var(--mono); font-size: 0.78rem; color: var(--muted); white-space: nowrap; }
.guide-section-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    color: var(--text);
    font-weight: 700;
    padding: 0.7rem 0.85rem 0.4rem 1rem;
    border-top: 1px solid var(--border);
    border-left: 3px solid var(--accent);
    background: var(--surface2);
}
.guide-section-label:first-child { border-top: none; }

/* ---- Footer ---- */
footer {
    text-align: center;
    padding: 1.5rem;
    font-size: 0.75rem;
    color: var(--muted);
    border-top: 1px solid var(--border);
    margin-top: 1rem;
}
"""

def _active_env_vars():
    """Return set of env var names currently set to a non-empty value."""
    candidates = (
        "IMAP_SERVER", "IMAP_PORT", "EMAIL_USER", "EMAIL_PASS",
        "EMAIL_ADDRESS", "MAILBOX", "CLEAN_DAYS", "MAILBOX_CONFIGS",
        "SEND_TELEGRAM_NOTIFICATIONS", "TELEGRAM_BOT_TOKEN",
        "CLEAN_EMAIL_TELEGRAM_CHAT_ID", "TELEGRAM_CHAT_ID", "TELEGRAM_TIMEOUT",
        "TELEGRAM_NOTIFY_MODE", "TELEGRAM_NOTIFY_ONLY_IF_DELETED",
        "SCHEDULE_MIN", "SCHEDULE_HOUR", "SCHEDULE_DAY",
        "DIGEST_SCHEDULE_MIN", "DIGEST_SCHEDULE_HOUR", "DIGEST_SCHEDULE_DAY",
        "WEB_PORT", "TZ",
    )
    return {k for k in candidates if os.getenv(k)}


def _render_guide(active_vars):
    """Return the collapsible env vars reference HTML."""
    def row(var, default, desc):
        dot = (
            "<span class='dot dot-ok' title='Set in this container' "
            "style='margin-right:0.35rem;vertical-align:middle'></span>"
            if var in active_vars else
            "<span class='dot dot-muted' title='Not configured' "
            "style='margin-right:0.35rem;vertical-align:middle'></span>"
        )
        return (
            f"<tr><td>{dot}{escape(var)}</td>"
            f"<td>{escape(str(default))}</td>"
            f"<td>{desc}</td></tr>"
        )

    def section(label):
        return f"<tr><td colspan='3' class='guide-section-label'>{escape(label)}</td></tr>"

    rows = "".join([
        section("IMAP / Mailbox"),
        row("IMAP_SERVER",    "—",         "IMAP server hostname or IP. <strong>Required.</strong>"),
        row("IMAP_PORT",      "993",        "IMAP SSL port."),
        row("EMAIL_USER",     "—",         "<strong>Required.</strong> Username for IMAP login."),
        row("EMAIL_PASS",     "—",         "<strong>Required.</strong> Password for IMAP login."),
        row("EMAIL_ADDRESS",  "EMAIL_USER", "Display label used in logs and notifications."),
        row("MAILBOX",        "INBOX",      "IMAP folder to clean."),
        row("CLEAN_DAYS",     "10",         "Delete emails older than this many days. Overridden by <code>--days</code> CLI argument."),
        row("MAILBOX_CONFIGS","—",          "JSON array for multi-mailbox mode. Each entry: <code>imap_server</code>, <code>email_user</code>, <code>email_pass</code>, and optionally <code>imap_port</code>, <code>email_address</code>, <code>mailbox</code>, <code>clean_days</code>."),
        section("Schedule (cron)"),
        row("SCHEDULE_MIN",   "0",  "Cron minute (0–59)."),
        row("SCHEDULE_HOUR",  "0",  "Cron hour (0–23)."),
        row("SCHEDULE_DAY",   "0",  "Cron weekday — 0/7 = Sunday … 6 = Saturday. Use <code>*</code> for every day."),
        section("Telegram Notifications"),
        row("SEND_TELEGRAM_NOTIFICATIONS", "false", "Enable Telegram notifications. Accepted: <code>1</code>, <code>true</code>, <code>yes</code>, <code>on</code>."),
        row("TELEGRAM_BOT_TOKEN",          "—",     "Bot token from @BotFather. Required when notifications are enabled."),
        row("TELEGRAM_CHAT_ID",            "—",     "Chat ID to send notifications to."),
        row("CLEAN_EMAIL_TELEGRAM_CHAT_ID","—",     "Alternative chat ID; takes priority over <code>TELEGRAM_CHAT_ID</code>."),
        row("TELEGRAM_TIMEOUT",            "10",    "Timeout in seconds for Telegram API calls."),
        row("TELEGRAM_NOTIFY_MODE",        "always","<code>always</code>: notify after every run. <code>digest</code>: accumulate results and send on a separate schedule."),
        row("TELEGRAM_NOTIFY_ONLY_IF_DELETED","false","When <code>true</code>, skip notifications for runs where no emails were deleted."),
        section("Digest Schedule (TELEGRAM_NOTIFY_MODE=digest only)"),
        row("DIGEST_SCHEDULE_MIN",  "0", "Cron minute for the digest send."),
        row("DIGEST_SCHEDULE_HOUR", "8", "Cron hour for the digest send."),
        row("DIGEST_SCHEDULE_DAY",  "0", "Cron weekday for the digest send (same format as <code>SCHEDULE_DAY</code>)."),
        section("Web Status Page"),
        row("WEB_PORT", "8080", "Internal port for the status page. Always started by the container; override only if 8080 conflicts."),
        section("Timezone"),
        row("TZ", "UTC", "Container timezone. Affects all timestamps written by the script (e.g. Last Run). Example: <code>Europe/Rome</code>, <code>America/New_York</code>. The status page clock always uses the browser's local time regardless of this setting."),
    ])

    return f"""
    <details>
        <summary>Environment Variables Reference</summary>
        <div class="guide-body">
            <table>
                <thead>
                    <tr><th>Variable</th><th>Default</th><th>Description</th></tr>
                </thead>
                <tbody>{rows}</tbody>
            </table>
        </div>
    </details>"""


_ENVELOPE_ICON = """<svg width="22" height="22" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2" y="4" width="20" height="16" rx="2"/>
  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
</svg>"""


def _render_html():
    mailboxes = _get_mailbox_configs()
    cron_expr, schedule_desc = _get_schedule()
    last_run = _get_last_run()
    tg_ok, tg_detail, tg_mode, tg_only_deleted = _telegram_status()
    active_vars = _active_env_vars()

    # ---- Mailboxes table ----
    mb_rows = ""
    for mb in mailboxes:
        mb_rows += (
            f"<tr>"
            f"<td>{escape(str(mb['email_address']))}</td>"
            f"<td>{escape(str(mb['imap_server']))}</td>"
            f"<td class='hide-mobile'>{escape(str(mb['imap_port']))}</td>"
            f"<td><code>{escape(str(mb['mailbox']))}</code></td>"
            f"<td>{escape(str(mb['clean_days']))} days</td>"
            f"</tr>"
        )

    # ---- Last run section ----
    if last_run:
        ts = escape(last_run.get("timestamp", "unknown"))
        run_rows = ""
        for r in last_run.get("results", []):
            st = r.get("status", "unknown")
            badge = "badge-ok" if st == "success" else "badge-err"
            dot   = "dot-ok"  if st == "success" else "dot-err"
            deleted  = r.get("deleted_count", 0)
            duration = r.get("duration_seconds", 0)
            error    = r.get("error_message") or ""
            run_rows += (
                f"<tr>"
                f"<td>{escape(str(r.get('mailbox_address', '')))}</td>"
                f"<td><code>{escape(str(r.get('mailbox_name', 'INBOX')))}</code></td>"
                f"<td><span class='badge {badge}'>{escape(st)}</span></td>"
                f"<td>{deleted}</td>"
                f"<td class='hide-mobile'>{float(duration):.2f}s</td>"
                f"<td class='{'cell-err' if error else 'cell-muted'}'>{escape(error) if error else '—'}</td>"
                f"</tr>"
            )
        run_body = (
            f"""<div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Mailbox</th><th>Folder</th><th>Status</th>
                            <th>Deleted</th><th class="hide-mobile">Duration</th><th>Error</th>
                        </tr>
                    </thead>
                    <tbody>{run_rows}</tbody>
                </table>
            </div>"""
            if run_rows else
            "<p class='empty'>Run recorded but no mailbox results found — check container logs for details.</p>"
        )
        last_run_html = f"""
        <section class="card">
            <p class="card-title">Last Run &nbsp;·&nbsp; {ts}</p>
            {run_body}
        </section>"""
    else:
        last_run_html = """
        <section class="card">
            <p class="card-title">Last Run</p>
            <p class="empty">No run data yet — the cleanup will execute at the next scheduled time.</p>
        </section>"""

    tg_badge = "badge-ok" if tg_ok else "badge-muted"
    tg_dot   = "dot-ok"  if tg_ok else "dot-muted"
    tg_label = "Enabled" if tg_ok else "Not configured"

    mode_label = "Digest" if tg_mode == "digest" else "Per run"
    mode_badge = "badge-count" if tg_mode == "digest" else "badge-muted"

    filter_label = "Only if deleted" if tg_only_deleted else "Always"
    filter_badge = "badge-count" if tg_only_deleted else "badge-muted"

    if tg_mode == "digest":
        digest_min  = os.getenv("DIGEST_SCHEDULE_MIN", "0")
        digest_hour = os.getenv("DIGEST_SCHEDULE_HOUR", "8")
        digest_day  = os.getenv("DIGEST_SCHEDULE_DAY", "0")
        day_names = {
            "0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
            "4": "Thursday", "5": "Friday", "6": "Saturday", "*": "every day",
        }
        try:
            h, m = int(digest_hour), int(digest_min)
            digest_mini_box = (
                f"<div class='mini-box'>"
                f"<span class='stat-label'>Digest schedule</span>"
                f"<span class='stat-value' style='font-size:0.85rem'>"
                f"Every {escape(day_names.get(digest_day, f'day {digest_day}'))} at {h:02d}:{m:02d}"
                f"</span></div>"
            )
        except ValueError:
            digest_mini_box = ""
    else:
        digest_mini_box = ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="60">
    <title>Clean Mail Automation</title>
    <link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233b82f6' stroke-width='1.75' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='2' y='4' width='20' height='16' rx='2' fill='%230f172a'/%3E%3Cpath d='m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7'/%3E%3C/svg%3E">
    <style>{_CSS}</style>
</head>
<body>

<header>
    <div class="logo">
        {_ENVELOPE_ICON}
        <h1>Clean <em>Mail</em> Automation</h1>
        <span class="badge badge-muted" style="font-size:0.68rem;margin-left:0.25rem">v{APP_VERSION}</span>
    </div>
    <div class="meta">
        Auto-refreshes every 60&thinsp;s<br>
        <span id="clock"></span>
    </div>
</header>

<main>

    <div class="grid-2">

        <section class="card">
            <p class="card-title">Schedule</p>
            <div class="mini-grid">
                <div class="mini-box" style="grid-column:1/-1">
                    <span class="stat-label">Cron expression</span>
                    <span class="stat-value"><code>{escape(cron_expr)}</code></span>
                </div>
                <div class="mini-box" style="grid-column:1/-1">
                    <span class="stat-label">Human-readable</span>
                    <span class="stat-value">{escape(schedule_desc)}</span>
                </div>
            </div>
        </section>

        <section class="card">
            <p class="card-title">Notifications</p>
            <div class="mini-grid">
                <div class="mini-box">
                    <div class="mini-box-split">
                        <div class="mini-box-main">
                            <span class="stat-label">Telegram</span>
                            <span class="stat-value">
                                <span class="dot {tg_dot}"></span>
                                {tg_label}
                            </span>
                        </div>
                        {f"""<div class="mini-actions">
                            <a class="btn-action" href="/action/test-notify" onclick="return confirm('Send a test Telegram notification?')">
                                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>
                                Test
                            </a>
                        </div>""" if tg_ok else ""}
                    </div>
                </div>
                <div class="mini-box">
                    <div class="mini-box-split">
                        <div class="mini-box-main">
                            <span class="stat-label">Notify mode</span>
                            <span class="stat-value">{mode_label}</span>
                        </div>
                        {f"""<div class="mini-actions">
                            <a class="btn-action" href="/action/send-digest" onclick="return confirm('Send the accumulated digest now and clear it?')">
                                <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 16 12 14 15 10 15 8 12 2 12"/><path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11z"/></svg>
                                Send now
                            </a>
                        </div>""" if tg_ok and tg_mode == "digest" else ""}
                    </div>
                </div>
                <div class="mini-box">
                    <span class="stat-label">Send condition</span>
                    <span class="stat-value">{filter_label}</span>
                </div>
                {digest_mini_box}
            </div>
        </section>

    </div>

    <section class="card">
        <div class="card-header">
            <p class="card-title">Mailboxes</p>
            <span class="badge badge-count">{len(mailboxes)}</span>
        </div>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Email address</th>
                        <th>IMAP server</th>
                        <th class="hide-mobile">Port</th>
                        <th>Folder</th>
                        <th>Retention</th>
                    </tr>
                </thead>
                <tbody>{mb_rows}</tbody>
            </table>
        </div>
    </section>

    {last_run_html}

    {_render_guide(active_vars)}

</main>

<button id="totop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" title="Back to top" aria-label="Back to top">&#9650;</button>

<script>
// ---- Clock (browser local time) ----
function _tick() {{
    var d = new Date();
    var pad = function(n) {{ return n.toString().padStart(2,'0'); }};
    document.getElementById('clock').textContent =
        d.getFullYear() + '-' + pad(d.getMonth()+1) + '-' + pad(d.getDate()) +
        ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds());
}}
_tick();
setInterval(_tick, 1000);

// ---- Back-to-top ----
window.addEventListener('scroll', function() {{
    document.getElementById('totop').style.display = window.scrollY > 300 ? 'flex' : 'none';
}});

// ---- Guide: persist open/closed state + smooth scroll on open ----
(function() {{
    var details = document.querySelector('details');
    if (!details) return;
    if (localStorage.getItem('guide_open') === '1') details.open = true;
    details.addEventListener('toggle', function() {{
        localStorage.setItem('guide_open', details.open ? '1' : '0');
        if (details.open) {{
            setTimeout(function() {{
                details.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}, 50);
        }}
    }});
}})();
</script>

<footer>
    <a href="https://github.com/gioxx/clean-mail-automation" target="_blank" rel="noopener">
        gioxx/clean-mail-automation
    </a>
    &nbsp;&middot;&nbsp; MIT License
</footer>

</body>
</html>"""


# ---------------------------------------------------------------------------
# HTTP server
# ---------------------------------------------------------------------------

def _run_action(args):
    """Run clean_email.py with given args, return (success, output)."""
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "clean_email.py")
    try:
        result = subprocess.run(
            [sys.executable, script] + args,
            capture_output=True, text=True, timeout=30,
        )
        return result.returncode == 0, (result.stdout + result.stderr).strip()
    except Exception as e:
        return False, str(e)


def _send_test_notification():
    """Send a test Telegram message directly from the status server."""
    import urllib.parse
    import urllib.request
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("CLEAN_EMAIL_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False, "Telegram not configured"
    msg = f"Clean Mail Automation v{APP_VERSION} — test notification. Everything is working correctly."
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": msg}).encode()
    try:
        with urllib.request.urlopen(
            urllib.request.Request(api_url, data=payload, method="POST"), timeout=10
        ) as r:
            return r.status == 200, "sent" if r.status == 200 else f"HTTP {r.status}"
    except Exception as e:
        return False, str(e)


class _StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/status", "/index.html"):
            body = _render_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        elif self.path == "/action/send-digest":
            ok, out = _run_action(["--send-digest", "--force"])
            print(f"[action/send-digest] ok={ok} {out}", flush=True)
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()

        elif self.path == "/action/test-notify":
            ok, out = _send_test_notification()
            print(f"[action/test-notify] ok={ok} {out}", flush=True)
            self.send_response(302)
            self.send_header("Location", "/")
            self.end_headers()

        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):  # suppress per-request access logs
        pass


if __name__ == "__main__":
    port_raw = os.getenv("WEB_PORT", "8080")
    try:
        port = int(port_raw)
        if port < 1 or port > 65535:
            raise ValueError
    except ValueError:
        print(f"Invalid WEB_PORT value '{port_raw}', defaulting to 8080.", flush=True)
        port = 8080

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", port), _StatusHandler) as httpd:
        print(f"Status server listening on port {port}", flush=True)
        httpd.serve_forever()
