#!/bin/bash
# Install the Minecraft Control agent as a per-user LaunchAgent on the child's Mac.
# Run this ON THE CHILD'S MAC, logged in as the child's account:
#     bash install.sh
set -euo pipefail

LABEL="com.nr10.minecraftpause"
APP_DIR="$HOME/.minecraft-pause"
AGENT_DST="$APP_DIR/agent.py"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PORT="${MCPAUSE_PORT:-8731}"

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON="$(command -v python3 || true)"
if [ -z "$PYTHON" ]; then
  echo "python3 not found. Install the Command Line Tools:  xcode-select --install" >&2
  exit 1
fi

echo "==> Installing to $APP_DIR"
mkdir -p "$APP_DIR"
cp "$SRC_DIR/agent.py" "$AGENT_DST"

echo "==> Writing LaunchAgent $PLIST"
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>$AGENT_DST</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>MCPAUSE_PORT</key><string>$PORT</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ProcessType</key><string>Background</string>
  <key>StandardOutPath</key><string>$APP_DIR/agent.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/agent.log</string>
</dict>
</plist>
PLIST_EOF

UID_NUM="$(id -u)"
echo "==> (Re)loading service"
launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$UID_NUM" "$PLIST"
launchctl enable "gui/$UID_NUM/$LABEL" 2>/dev/null || true

sleep 1
TOKEN="$(cat "$APP_DIR/token" 2>/dev/null || echo '???')"
IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || echo '<mac-ip>')"

cat <<DONE

==> Done. The agent is running and will auto-start at login.

   Open this on the parent's iPhone (same Wi-Fi), then
   Share -> "Add to Home Screen" for a one-tap icon:

      http://$IP:$PORT/?t=$TOKEN

   Logs:        $APP_DIR/agent.log
   Uninstall:   bash uninstall.sh
DONE
