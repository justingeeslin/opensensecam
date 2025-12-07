#!/usr/bin/env bash
set -e

APP_ID="hello-pi"

USER_HOME="$(eval echo ~$USER)"

rm -rf "$USER_HOME/.local/share/$APP_ID"
rm -f  "$USER_HOME/.local/share/applications/$APP_ID.desktop"

echo "🗑️  $APP_ID removed"