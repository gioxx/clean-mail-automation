#!/usr/bin/env python3
"""Optional HTTP status page for clean-mail-automation.

Starts only when the WEB_PORT environment variable is set.
Reads configuration from env vars and last-run state from STATE_FILE.
"""

import datetime
import http.server
import json
import os
import socketserver
from html import escape

STATE_FILE = "/tmp/clean_mail_last_run.json"
DEFAULT_MAILBOX = "INBOX"


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
    """Return (enabled: bool, detail: str)."""
    gate = os.getenv("SEND_TELEGRAM_NOTIFICATIONS", "false").strip().lower() in {
        "1", "true", "yes", "on"
    }
    token = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    chat_id = bool(os.getenv("CLEAN_EMAIL_TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID"))

    if not gate:
        return False, "disabled via SEND_TELEGRAM_NOTIFICATIONS"
    if not token:
        return False, "TELEGRAM_BOT_TOKEN not set"
    if not chat_id:
        return False, "TELEGRAM_CHAT_ID not set"
    return True, "configured"


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
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1.25rem; }
@media (max-width: 660px) { .grid-2 { grid-template-columns: 1fr; } }

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

_ENVELOPE_ICON = """<svg width="22" height="22" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
  <rect x="2" y="4" width="20" height="16" rx="2"/>
  <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/>
</svg>"""


def _render_html():
    mailboxes = _get_mailbox_configs()
    cron_expr, schedule_desc = _get_schedule()
    last_run = _get_last_run()
    tg_ok, tg_detail = _telegram_status()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ---- Mailboxes table ----
    mb_rows = ""
    for mb in mailboxes:
        mb_rows += (
            f"<tr>"
            f"<td>{escape(str(mb['email_address']))}</td>"
            f"<td>{escape(str(mb['imap_server']))}</td>"
            f"<td>{escape(str(mb['imap_port']))}</td>"
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
                f"<td>{float(duration):.2f}s</td>"
                f"<td class='{'cell-err' if error else 'cell-muted'}'>{escape(error) if error else '—'}</td>"
                f"</tr>"
            )
        last_run_html = f"""
        <section class="card">
            <p class="card-title">Last Run &nbsp;·&nbsp; {ts}</p>
            <div class="table-wrap">
                <table>
                    <thead>
                        <tr>
                            <th>Mailbox</th><th>Folder</th><th>Status</th>
                            <th>Deleted</th><th>Duration</th><th>Error</th>
                        </tr>
                    </thead>
                    <tbody>{run_rows}</tbody>
                </table>
            </div>
        </section>"""
    else:
        last_run_html = """
        <section class="card">
            <p class="card-title">Last Run</p>
            <p class="empty">No run data yet — the cleanup will execute at the next scheduled time.</p>
        </section>"""

    tg_badge = "badge-ok" if tg_ok else "badge-muted"
    tg_dot   = "dot-ok"  if tg_ok else "dot-muted"
    tg_label = "Enabled"  if tg_ok else "Disabled"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="60">
    <title>Clean Mail Automation</title>
    <style>{_CSS}</style>
</head>
<body>

<header>
    <div class="logo">
        {_ENVELOPE_ICON}
        <h1>Clean <em>Mail</em> Automation</h1>
    </div>
    <div class="meta">
        Auto-refreshes every 60&thinsp;s<br>
        {escape(now)}
    </div>
</header>

<main>

    <div class="grid-2">

        <section class="card">
            <p class="card-title">Schedule</p>
            <div class="stat-row">
                <span class="stat-label">Cron expression</span>
                <span class="stat-value"><code>{escape(cron_expr)}</code></span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Human-readable</span>
                <span class="stat-value">{escape(schedule_desc)}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Mailboxes configured</span>
                <span class="stat-value">{len(mailboxes)}</span>
            </div>
        </section>

        <section class="card">
            <p class="card-title">Notifications</p>
            <div class="stat-row">
                <span class="stat-label">Telegram</span>
                <span class="stat-value">
                    <span class="dot {tg_dot}"></span>
                    <span class="badge {tg_badge}">{tg_label}</span>
                </span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Detail</span>
                <span class="stat-value" style="font-size:0.82rem;color:var(--muted)">{escape(tg_detail)}</span>
            </div>
        </section>

    </div>

    <section class="card">
        <p class="card-title">Mailboxes</p>
        <div class="table-wrap">
            <table>
                <thead>
                    <tr>
                        <th>Email address</th>
                        <th>IMAP server</th>
                        <th>Port</th>
                        <th>Folder</th>
                        <th>Retention</th>
                    </tr>
                </thead>
                <tbody>{mb_rows}</tbody>
            </table>
        </div>
    </section>

    {last_run_html}

</main>

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

class _StatusHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/status", "/index.html"):
            self.send_response(404)
            self.end_headers()
            return
        body = _render_html().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

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
