#!/bin/bash
# Remove the Minecraft Control agent. Run on the child's Mac as the child's user.
set -euo pipefail
LABEL="com.nr10.minecraftpause"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
UID_NUM="$(id -u)"

launchctl bootout "gui/$UID_NUM/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
echo "Removed service. App files left in ~/.minecraft-pause (delete manually if desired)."
