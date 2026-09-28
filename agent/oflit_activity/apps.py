"""Application observation and name normalization.

Best-effort only. Under Wayland/GNOME there is no reliable, privilege-free way
to know which window is *foreground*, so this module deliberately reports only
what it can prove: which relevant processes are *running* under a given child
session. Events are recorded with evidence ``process_running`` — never
``foreground_application`` — so reports never claim the child was "using" an
app when we only know it was launched.

Only a curated allowlist of relevant desktop applications is reported. The
process table is never dumped wholesale.
"""

from __future__ import annotations

import subprocess

# Map an executable / comm name to a friendly application label. Only apps in
# this table are ever reported.
_APP_MAP = {
    "chrome": "Google Chrome",
    "google-chrome": "Google Chrome",
    "chrome_crashpad": None,          # noise — ignore
    "chromium": "Chromium",
    "nautilus": "Files",
    "org.gnome.nautilus": "Files",
    "gnome-text-editor": "Text Editor",
    "gedit": "Text Editor",
    "eog": "Image Viewer",
    "org.gnome.eog": "Image Viewer",
    "evince": "Document Viewer",
    "libreoffice": "LibreOffice",
    "soffice.bin": "LibreOffice",
    "gnome-calculator": "Calculator",
    "totem": "Videos",
    "vlc": "VLC",
    "gimp": "GIMP",
}

# Executable-path fragments mapped to labels (covers absolute paths).
_PATH_HINTS = [
    ("/opt/google/chrome/chrome", "Google Chrome"),
    ("/usr/bin/nautilus", "Files"),
    ("/usr/lib/libreoffice", "LibreOffice"),
]


def normalize_app(name_or_path: str):
    """Return a friendly label, or None if the process is not a reported app."""
    if not name_or_path:
        return None
    raw = name_or_path.strip()
    base = raw.rsplit("/", 1)[-1].split()[0] if raw else ""
    if base in _APP_MAP:
        return _APP_MAP[base]
    for fragment, label in _PATH_HINTS:
        if fragment in raw:
            return label
    return None


def running_apps_for_user(username: str) -> set:
    """Return the set of friendly app labels currently running for a user.

    Uses ``ps`` scoped to the user. Never returns raw process names; only
    entries present in the curated allowlist are surfaced.
    """
    try:
        proc = subprocess.run(
            ["ps", "-u", username, "-o", "comm="],
            capture_output=True, text=True, timeout=8, check=False,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return set()
    if proc.returncode != 0:
        return set()
    labels = set()
    for line in proc.stdout.splitlines():
        label = normalize_app(line.strip())
        if label:
            labels.add(label)
    return labels
