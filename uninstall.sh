#!/usr/bin/env bash
set -euo pipefail

APP_ID="hello-pi"
SERVICE_NAME="hello-pi.service"
SERVICE_USER="hello-pi"

APP_DIR="/opt/$APP_ID"
DESKTOP_DEST="/usr/share/applications/$APP_ID.desktop"
ICON_DEST="/usr/share/pixmaps/$APP_ID.png"
SERVICE_DEST="/etc/systemd/system/$SERVICE_NAME"

STATE_DIR="/var/lib/$APP_ID"

# Require root for system uninstall
if [ "$(id -u)" -ne 0 ]; then
  echo "❌ This is a system uninstall. Run with sudo:"
  echo "   sudo $0"
  exit 1
fi

echo "🧹 Uninstalling system app: $APP_ID"

# Stop/disable service if present
if systemctl list-unit-files | grep -q "^$SERVICE_NAME"; then
  echo "🛑 Stopping/disabling service: $SERVICE_NAME"
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME" 2>/dev/null || true
fi

# Remove service unit file
if [ -f "$SERVICE_DEST" ]; then
  echo "🗑️  Removing service file: $SERVICE_DEST"
  rm -f "$SERVICE_DEST"
  systemctl daemon-reload
fi

# Remove app files
if [ -d "$APP_DIR" ]; then
  echo "🗑️  Removing app dir: $APP_DIR"
  rm -rf "$APP_DIR"
fi

# Remove desktop entry
if [ -f "$DESKTOP_DEST" ]; then
  echo "🗑️  Removing desktop entry: $DESKTOP_DEST"
  rm -f "$DESKTOP_DEST"
fi

# Remove icon (optional)
if [ -f "$ICON_DEST" ]; then
  echo "🗑️  Removing icon: $ICON_DEST"
  rm -f "$ICON_DEST"
fi

# Remove state directory (optional but usually desired)
if [ -d "$STATE_DIR" ]; then
  echo "🗑️  Removing state dir: $STATE_DIR"
  rm -rf "$STATE_DIR"
fi

# Remove the dedicated service user (optional)
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
  echo "👤 Removing service user: $SERVICE_USER"
  # userdel -r removes home dir if it matches (we also removed /var/lib/$APP_ID above)
  userdel "$SERVICE_USER" 2>/dev/null || true
fi

# Refresh desktop database if available
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database /usr/share/applications || true
fi

echo "✅ $APP_ID removed"