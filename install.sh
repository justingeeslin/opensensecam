#!/usr/bin/env bash
set -euo pipefail

# ==============================
# CONFIG (ONLY CHANGE THESE)
# ==============================
APP_ID="hello-pi"
SERVICE_NAME="hello-pi.service"     # name of your .service file in src/
SERVICE_USER="hello-pi"

# ==============================
# DERIVED PATHS
# ==============================
SRC_DIR="./src"
DESKTOP_SRC="./$APP_ID.desktop"
ICON_SRC="./icon.png"

APP_DIR="/opt/$APP_ID"
SERVICE_SRC="$SRC_DIR/$SERVICE_NAME"
SERVICE_DEST="/etc/systemd/system/$SERVICE_NAME"

DESKTOP_DEST="/usr/share/applications/$APP_ID.desktop"
ICON_DEST="/usr/share/pixmaps/$APP_ID.png"

# ==============================
# REQUIRE ROOT (system install)
# ==============================
if [ "$(id -u)" -ne 0 ]; then
  echo "❌ This installer now performs a system install. Run with sudo:"
  echo "   sudo $0"
  exit 1
fi

echo "📦 Installing system app: $APP_ID"
echo "   App dir:        $APP_DIR"
echo "   Desktop entry:  $DESKTOP_DEST"
echo "   Service:        $SERVICE_DEST"
echo "   Service user:   $SERVICE_USER"

# ==============================
# CREATE DEDICATED SERVICE USER
# ==============================
if id -u "$SERVICE_USER" >/dev/null 2>&1; then
  echo "👤 Service user exists: $SERVICE_USER"
else
  echo "👤 Creating service user: $SERVICE_USER"
  useradd \
    --system \
    --home "/var/lib/$APP_ID" \
    --create-home \
    --shell /usr/sbin/nologin \
    "$SERVICE_USER"
fi

# ==============================
# INSTALL APP FILES (system-wide)
# ==============================
echo "🗂  Installing app files to $APP_DIR..."
mkdir -p "$APP_DIR"
rm -rf "$APP_DIR/src"
cp -r "$SRC_DIR" "$APP_DIR/"

# Make python scripts executable if you rely on that (optional)
if [ -f "$APP_DIR/src/index.py" ]; then
  chmod +x "$APP_DIR/src/index.py"
fi

# Keep app code owned by root (read-only-ish)
chown -R root:root "$APP_DIR"
chmod -R a+rX "$APP_DIR"

# ==============================
# INSTALL DESKTOP ENTRY (system-wide)
# ==============================
if [ -f "$DESKTOP_SRC" ]; then
  echo "🖥  Installing desktop entry to $DESKTOP_DEST..."
  cp "$DESKTOP_SRC" "$DESKTOP_DEST"
  chmod 644 "$DESKTOP_DEST"
else
  echo "ℹ️ No desktop file found at $DESKTOP_SRC – skipping."
fi

# ==============================
# INSTALL ICON (system-wide)
# ==============================
if [ -f "$ICON_SRC" ]; then
  echo "🖼️  Installing icon to $ICON_DEST..."
  cp "$ICON_SRC" "$ICON_DEST"
  chmod 644 "$ICON_DEST"
else
  echo "ℹ️ No icon found at $ICON_SRC – skipping."
fi

# ==============================
# INSTALL SYSTEMD SERVICE
# ==============================
if [ -f "$SERVICE_SRC" ]; then
  echo "🔧 Found service file: $SERVICE_SRC"
  echo "🛠  Installing systemd service to $SERVICE_DEST..."
  cp "$SERVICE_SRC" "$SERVICE_DEST"
  chmod 644 "$SERVICE_DEST"

  systemctl daemon-reload
  systemctl enable "$SERVICE_NAME"

  echo "✅ Service installed and enabled: $SERVICE_NAME"
  echo "   Start it with: sudo systemctl start $SERVICE_NAME"
else
  echo "ℹ️ No service file found at $SERVICE_SRC – skipping system service install."
fi

echo "✅ Install complete!"