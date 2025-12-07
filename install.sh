#!/usr/bin/env bash
set -e

# ==============================
# CONFIG (ONLY CHANGE THESE)
# ==============================
APP_ID="hello-pi"
SERVICE_NAME="hello-pi.service"   # name of your .service file in src/

# ==============================
# DERIVED PATHS (USUALLY NO NEED TO CHANGE)
# ==============================
# If run with sudo, install app for the *real* user, not root
TARGET_USER="${SUDO_USER:-$USER}"
USER_HOME="$(eval echo ~"$TARGET_USER")"

APP_DIR="$USER_HOME/.local/share/$APP_ID"
DESKTOP_DIR="$USER_HOME/.local/share/applications"

SRC_DIR="./src"
DESKTOP_SRC="./$APP_ID.desktop"
ICON_SRC="./icon.png"

SCRIPT_DEST_DIR="$APP_DIR/src"
DESKTOP_DEST="$DESKTOP_DIR/$APP_ID.desktop"
ICON_DEST="$APP_DIR/icon.png"

SERVICE_SRC="$SRC_DIR/$SERVICE_NAME"
SERVICE_DEST="/etc/systemd/system/$SERVICE_NAME"

echo "📦 Installing $APP_ID for user: $TARGET_USER"
echo "   App dir:        $APP_DIR"
echo "   Desktop entry:  $DESKTOP_DEST"

# ==============================
# INSTALL APP FILES (per-user)
# ==============================
mkdir -p "$SCRIPT_DEST_DIR"
mkdir -p "$DESKTOP_DIR"

# Copy src/ tree into APP_DIR
cp -r "$SRC_DIR/" "$APP_DIR/"

# Copy .desktop launcher
cp "$DESKTOP_SRC" "$DESKTOP_DEST"

# Optional icon
if [ -f "$ICON_SRC" ]; then
  cp "$ICON_SRC" "$ICON_DEST"
  echo "🖼️  Icon installed"
fi

# Permissions: make launcher and main script executable
if [ -f "$SCRIPT_DEST_DIR/index.py" ]; then
  chmod +x "$SCRIPT_DEST_DIR/index.py"
fi
chmod +x "$DESKTOP_DEST"

# Make sure files are owned by the target user if run with sudo
if [ "$(id -u)" -eq 0 ] && [ -n "$SUDO_USER" ]; then
  chown -R "$SUDO_USER":"$SUDO_USER" "$APP_DIR" "$DESKTOP_DEST"
fi

# ==============================
# INSTALL SYSTEMD SERVICE (optional, needs root)
# ==============================
if [ -f "$SERVICE_SRC" ]; then
  echo "🔧 Found service file in src/: $SERVICE_SRC"

  if [ "$(id -u)" -ne 0 ]; then
    echo "⚠️  Not root: skipping systemd service install."
    echo "    To install the service, run: sudo $0"
  else
    echo "🛠  Installing systemd service to $SERVICE_DEST..."
    cp "$SERVICE_SRC" "$SERVICE_DEST"
    chmod 644 "$SERVICE_DEST"

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"

    echo "✅ Systemd service installed and enabled: $SERVICE_NAME"
    echo "   You can start it with: sudo systemctl start $SERVICE_NAME"
  fi
else
  echo "ℹ️ No service file found at $SERVICE_SRC – skipping system service install."
fi

# ==============================
# REFRESH MENU (for the real user)
# ==============================
if command -v lxpanelctl >/dev/null 2>&1; then
  if [ "$(id -u)" -eq 0 ] && [ -n "$SUDO_USER" ]; then
    # Refresh panel as the desktop user if run under sudo
    sudo -u "$SUDO_USER" lxpanelctl restart || true
  else
    lxpanelctl restart || true
  fi
else
  echo "ℹ️ lxpanelctl not found. Log out and back in to refresh the menu."
fi

echo "✅ Install complete!"
echo "➡️ You should now see '$APP_ID' in the menu."