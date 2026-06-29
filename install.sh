#!/usr/bin/env bash
#
# setup-claude-telemetry.sh
# Asks for your full name, writes the Claude Code OpenTelemetry env into
# ~/.claude/settings.json (merging, not overwriting), then restarts Claude.
#
set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────
# Collector endpoint. Swap for your Tailscale IP if you locked down the
# public ports, e.g. http://100.x.y.z:4317
COLLECTOR="http://95.216.7.165:4317"

SETTINGS_DIR="$HOME/.claude"
SETTINGS_FILE="$SETTINGS_DIR/settings.json"

# ── 1. Ask for full name ────────────────────────────────────────────
read -rp "Enter your full name: " FULL_NAME
if [[ -z "${FULL_NAME// /}" ]]; then
  echo "Error: name cannot be empty." >&2
  exit 1
fi

# ── 2. Sanitize for OTEL_RESOURCE_ATTRIBUTES (no spaces / special chars) ──
# "Alice Brown" -> "alice_brown"; hostname -> safe token.
OWNER="$(printf '%s' "$FULL_NAME" \
  | tr '[:upper:]' '[:lower:]' \
  | sed -E 's/[^a-z0-9]+/_/g; s/^_+//; s/_+$//')"
HOSTID="$(hostname | sed -E 's/[^a-zA-Z0-9]+/_/g')"

# ── 3. Merge env into settings.json ─────────────────────────────────
mkdir -p "$SETTINGS_DIR"
[[ -f "$SETTINGS_FILE" ]] || echo '{}' > "$SETTINGS_FILE"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required to safely edit settings.json." >&2
  exit 1
fi

python3 - "$SETTINGS_FILE" "$COLLECTOR" "$OWNER" "$HOSTID" <<'PY'
import json, sys
path, collector, owner, hostid = sys.argv[1:5]
try:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        data = {}
except (json.JSONDecodeError, FileNotFoundError):
    data = {}

env = data.get("env", {})
if not isinstance(env, dict):
    env = {}

env.update({
    "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
    "OTEL_METRICS_EXPORTER": "otlp",
    "OTEL_LOGS_EXPORTER": "otlp",
    "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc",
    "OTEL_EXPORTER_OTLP_ENDPOINT": collector,
    "OTEL_RESOURCE_ATTRIBUTES": f"host.name={hostid},owner={owner}",
})
data["env"] = env

with open(path, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
PY

echo
echo "✓ Telemetry configured in $SETTINGS_FILE"
echo "    owner     = $OWNER"
echo "    host.name = $HOSTID"
echo "    endpoint  = $COLLECTOR"

# ── 4. Restart Claude Code ──────────────────────────────────────────
# Claude reads settings.json at startup, so a running session must be
# restarted to pick up the change.
echo
read -rp "Kill any running 'claude' sessions and start a fresh one now? [y/N] " ANS
if [[ "$ANS" =~ ^[Yy]$ ]]; then
  pkill -x claude 2>/dev/null || true
  sleep 1
  if command -v claude >/dev/null 2>&1; then
    echo "Starting a new Claude Code session..."
    exec claude
  else
    echo "'claude' not found in PATH. Open a new terminal and run 'claude' to apply."
  fi
else
  echo "Done. Exit your current Claude Code session and run 'claude' again to apply."
fi
