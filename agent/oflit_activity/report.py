"""Report formatting.

Two renderers share the OFL IT Lab Monitoring house style (emoji header,
aligned ``Key : value`` lines, Asia/Jakarta timestamps, "WIB"):

* :func:`render_telegram` — the final per-session summary sent to the existing
  OFL monitoring Telegram bot.
* :func:`render_status` — a live CLI view for ``child-activity status``.

Evidence wording is strict: submitted searches/prompts are labeled as direct
user actions, browser history as "visited", and proxy lines as "network
observation" — never conflated.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def _tz(name):
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - tz db missing -> UTC fallback
        return ZoneInfo("UTC")


def fmt_ts(epoch, tz):
    if not epoch:
        return "-"
    return datetime.fromtimestamp(epoch, tz).strftime("%d-%m-%Y %H:%M:%S WIB")


def fmt_clock(epoch, tz):
    if not epoch:
        return "--:--"
    return datetime.fromtimestamp(epoch, tz).strftime("%H:%M")


def fmt_duration(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    parts = []
    if h:
        parts.append(f"{h} jam")
    if m:
        parts.append(f"{m} menit")
    if not parts:
        parts.append(f"{s} detik")
    return " ".join(parts)


def _mark(text, truncated):
    return f"{text} […]" if truncated else text


def render_telegram(summary, timezone="Asia/Jakarta") -> str:
    tz = _tz(timezone)
    lines = []
    lines.append("🔵 AKTIVITAS USER — OFLIT i3")
    lines.append("")
    lines.append(f"User       : {summary.username}")
    lines.append(f"Login      : {fmt_ts(summary.login_epoch, tz)}")
    lines.append(f"Logout     : {fmt_ts(summary.logout_epoch, tz)}")
    lines.append(f"Durasi     : {fmt_duration(summary.duration_seconds)}")
    if summary.end_reason:
        lines.append(f"Berakhir   : {summary.end_reason}")
    lines.append("")

    # Browser — direct user actions first, then visited resources.
    if summary.google_searches or summary.chatgpt_prompts or summary.visited:
        lines.append("🌐 Browser")
        for epoch, text, trunc in summary.google_searches:
            lines.append(f"• Google Search: \"{_mark(text, trunc)}\"")
        if summary.chatgpt_prompts:
            lines.append("• ChatGPT prompt submitted:")
            for epoch, text, trunc in summary.chatgpt_prompts:
                lines.append(
                    f"  └─ {fmt_clock(epoch, tz)} — \"{_mark(text, trunc)}\""
                )
        for epoch, host in summary.visited:
            lines.append(f"• visited: {host}")
        lines.append("")

    if summary.apps:
        lines.append("🖥️ Aplikasi (terpantau berjalan)")
        for app in summary.apps:
            lines.append(f"• {app}")
        lines.append("")

    if summary.net_blocked or summary.net_visited:
        lines.append("🚫 Observasi jaringan (proxy)")
        for host in summary.net_blocked:
            lines.append(f"• blocked request observed: {host}")
        for host in summary.net_visited:
            lines.append(f"• network observation: {host}")
        lines.append("")

    lines.append(f"Perangkat  : {summary.device}")
    lines.append(f"Observer   : {summary.device}")
    return "\n".join(lines).rstrip() + "\n"


def render_status(summary, active=True, timezone="Asia/Jakarta") -> str:
    tz = _tz(timezone)
    lines = []
    lines.append("USER AKTIF" if active else "SESI SELESAI")
    lines.append("")
    lines.append(f"User      : {summary.username}")
    lines.append(f"Device    : {summary.device}")
    lines.append(f"Login     : {fmt_clock(summary.login_epoch, tz)}")
    if active:
        import time
        dur = max(0, int(time.time()) - summary.login_epoch)
    else:
        dur = summary.duration_seconds
    lines.append(f"Durasi    : {fmt_duration(dur)}")
    lines.append("")
    recent = []
    for epoch, text, trunc in summary.chatgpt_prompts:
        recent.append((epoch, "ChatGPT", f"submitted prompt: \"{_mark(text, trunc)}\""))
    for epoch, text, trunc in summary.google_searches:
        recent.append((epoch, "Google Search", f"query: \"{_mark(text, trunc)}\""))
    for epoch, host in summary.visited:
        recent.append((epoch, "Visited", host))
    recent.sort(reverse=True)
    if recent:
        lines.append("Aktivitas terbaru:")
        for epoch, kind, detail in recent[:10]:
            lines.append(f"  {fmt_clock(epoch, tz)} {kind}")
            lines.append(f"        {detail}")
    if summary.apps:
        lines.append("")
        lines.append("Aplikasi: " + ", ".join(summary.apps))
    return "\n".join(lines) + "\n"
