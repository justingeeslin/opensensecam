#!/usr/bin/env bash
set -e

# ==============================
# CONFIG (ONLY CHANGE THIS)
# ==============================
APP_ID="hello-pi"

# ==============================
# DERIVED PATHS (DO NOT CHANGE)
# ==============================
USER_HOME="$(eval echo ~$USER)"
APP_DIR="$USER_HOME/.local/share/$APP_ID"
DESKTOP_DIR="$USER_HOME/.local/share/applications"

SCRIPT_SRC="./src/"
DESKTOP_SRC="./$APP_ID.desktop"
ICON_SRC="./icon.png"

SCRIPT_DEST="$APP_DIR/src/index.py"
DESKTOP_DEST="$DESKTOP_DIR/$APP_ID.desktop"
ICON_DEST="$APP_DIR/icon.png"

# ==============================
# INSTALL
# ==============================
echo "📦 Installing $APP_ID..."

# Create directories
mkdir -p "$APP_DIR"
mkdir -p "$DESKTOP_DIR"

# Copy files
cp -r "$SCRIPT_SRC" "$SCRIPT_DEST"
cp "$DESKTOP_SRC" "$DESKTOP_DEST"

# Optional icon
if [ -f "$ICON_SRC" ]; then
  cp "$ICON_SRC" "$ICON_DEST"
  echo "🖼️  Icon installed"
fi

# Permissions
chmod +x "$SCRIPT_DEST"
chmod +x "$DESKTOP_DEST"

# ==============================
# REFRESH MENU
# ==============================
if command -v lxpanelctl >/dev/null 2>&1; then
  lxpanelctl restart
else
  echo "ℹ️ Log out and back in to refresh the menu."
fi

echo "✅ Install complete!"