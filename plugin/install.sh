#!/usr/bin/env bash
# Manual installer for the voxtral plugin (without going through Claude Code
# plugin marketplace). Run this from within the plugin/ directory.
set -euo pipefail

PLUGIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }

bold "1. Checking prerequisites"

if ! command -v uv >/dev/null 2>&1; then
  warn "uv is not installed. Install it with: curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
ok "uv $(uv --version | awk '{print $2}')"

if ! command -v afplay >/dev/null 2>&1; then
  warn "afplay not found — are you on macOS? This MCP plays audio via afplay."
  exit 1
fi
ok "afplay (macOS audio)"

if [[ "$(uname -m)" != "arm64" ]]; then
  warn "this plugin targets Apple Silicon (arm64). Detected: $(uname -m)."
  warn "MLX won't run on Intel Macs — performance will be very degraded or unsupported."
fi
ok "arch: $(uname -m)"

bold "2. Syncing the MCP server's Python venv (in $PLUGIN_DIR)"
(cd "$PLUGIN_DIR" && uv sync >/dev/null)
ok "venv ready at $PLUGIN_DIR/.venv"

bold "3. Next step — add to your project's .mcp.json"
cat <<EOF

Add this entry to the "mcpServers" object of your project's .mcp.json
(or ~/.claude.json for global use):

{
  "mcpServers": {
    "voxtral": {
      "command": "$PLUGIN_DIR/.venv/bin/voxtral-mcp",
      "env": {
        "VOXTRAL_MODEL": "mlx-community/Voxtral-4B-TTS-2603-mlx-4bit"
      }
    }
  }
}

Also copy the skill so /voice-mode works:

  mkdir -p ~/.claude/skills/voice-mode
  cp "$PLUGIN_DIR/skills/voice-mode/SKILL.md" ~/.claude/skills/voice-mode/SKILL.md

Then restart Claude Code / Cursor. In any conversation, say "parle-moi" or
type /voice-mode to activate spoken replies.

  Or — if you'd rather use the Claude Code plugin system (cleaner):
    /plugin marketplace add Vincweb/voxtral-mcp
    /plugin install voxtral@vincweb-tools

NOTE: The Voxtral model is released under CC BY-NC 4.0 (Mistral AI). Use is
restricted to non-commercial purposes — see LICENSE.
EOF
