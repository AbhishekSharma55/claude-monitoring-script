#!/usr/bin/env python3
"""
setup_claude_telemetry.py
Cross-platform (Windows / macOS / Linux) setup for Claude Code OpenTelemetry.

Asks for your full name, merges the telemetry env into ~/.claude/settings.json
(without overwriting existing settings), auto-labels the machine by hostname,
then helps you apply it -- restarting the terminal CLI if it's running, or
telling you how to reload the VS Code / Cursor extension if that's what you use.

Run:
  Linux / macOS : python3 setup_claude_telemetry.py
  Windows       : python  setup_claude_telemetry.py
"""

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

# -- Config -----------------------------------------------------------
# Collector endpoint. Swap for your Tailscale IP if you lock down the
# public ports, e.g. http://100.x.y.z:4317
COLLECTOR = "http://95.216.7.165:4317"


def main() -> None:
    settings_dir = Path.home() / ".claude"
    settings_file = settings_dir / "settings.json"

    # 1. Ask for full name
    try:
        full_name = input("Enter your full name: ").strip()
    except EOFError:
        full_name = ""
    if not full_name:
        print("Error: name cannot be empty.", file=sys.stderr)
        sys.exit(1)

    # 2. Sanitize for OTEL_RESOURCE_ATTRIBUTES (no spaces / special chars)
    #    "Alice Brown" -> "alice_brown"; hostname -> safe token.
    owner = re.sub(r"[^a-z0-9]+", "_", full_name.lower()).strip("_")
    hostid = re.sub(r"[^a-zA-Z0-9]+", "_", socket.gethostname())

    # 3. Merge env into settings.json (preserve anything already there)
    settings_dir.mkdir(parents=True, exist_ok=True)
    data: dict = {}
    if settings_file.exists():
        try:
            loaded = json.loads(settings_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except (json.JSONDecodeError, OSError):
            data = {}

    env = data.get("env", {})
    if not isinstance(env, dict):
        env = {}
    env.update({
        "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
        "OTEL_METRICS_EXPORTER": "otlp",
        "OTEL_LOGS_EXPORTER": "otlp",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
        "OTEL_EXPORTER_OTLP_ENDPOINT": COLLECTOR,
        "OTEL_RESOURCE_ATTRIBUTES": f"host.name={hostid},owner={owner}",
    })
    data["env"] = env

    settings_file.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    print()
    print(f"OK  Telemetry configured in {settings_file}")
    print(f"    owner     = {owner}")
    print(f"    host.name = {hostid}")
    print(f"    endpoint  = {COLLECTOR}")

    # 4. Apply the change. Claude Code reads settings.json at startup, so the
    #    running session must be restarted. Behavior depends on HOW it's run:
    #      - terminal CLI  -> we can kill + relaunch it
    #      - VS Code/Cursor extension -> it isn't a 'claude' process, so we
    #        can't kill it; the user reloads the editor window instead.
    print()
    try:
        ans = input(
            "Apply now by restarting Claude Code? [y/N] "
        ).strip()
    except EOFError:
        ans = ""

    if ans.lower() != "y":
        print_manual_guidance()
        return

    if claude_process_running():
        # A terminal CLI session is running -- restart it.
        kill_claude()
        time.sleep(1)
        claude = shutil.which("claude")
        if claude:
            print("Restarting Claude Code CLI...")
            if os.name == "nt":
                subprocess.run([claude])
            else:
                os.execvp(claude, [claude])
        else:
            print("Stopped the running session. Run 'claude' to start a new one.")
    else:
        # No CLI process found -- almost certainly the editor extension.
        print_extension_guidance()


def claude_process_running() -> bool:
    """True if a terminal 'claude' CLI process appears to be running."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq claude.exe"],
                capture_output=True, text=True,
            )
            return "claude.exe" in out.stdout
        else:
            r = subprocess.run(
                ["pgrep", "-x", "claude"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            return r.returncode == 0
    except FileNotFoundError:
        # pgrep/tasklist not available -- assume not running, fall back to guidance.
        return False


def kill_claude() -> None:
    """Best-effort stop of a running 'claude' CLI process, per OS."""
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/IM", "claude.exe"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        else:
            subprocess.run(
                ["pkill", "-x", "claude"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
    except FileNotFoundError:
        pass


def print_extension_guidance() -> None:
    print(
        "\nNo terminal 'claude' session was found -- you're likely using the\n"
        "VS Code / Cursor extension. To apply the new settings:\n"
        "  1. Open the Command Palette (Ctrl/Cmd + Shift + P)\n"
        "  2. Run: Developer: Reload Window\n"
        "  (or just close and reopen the editor)\n"
        "Then start a Claude Code chat and send a message.\n"
        "\nNote: if your editor is attached to a remote (SSH/WSL/devcontainer),\n"
        "this script must be run IN that same remote environment, because the\n"
        "extension reads ~/.claude/settings.json there, not on your laptop."
    )


def print_manual_guidance() -> None:
    print(
        "\nDone. To apply the settings:\n"
        "  - Terminal CLI: exit your session and run 'claude' again.\n"
        "  - VS Code / Cursor extension: Command Palette -> "
        "'Developer: Reload Window'."
    )


if __name__ == "__main__":
    main()
