#!/bin/sh
# notify_discord - run by Zmod's DISABLE_PLUGIN name=notify_discord

set -eu

NAME=notify_discord
PLUGIN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
CONFIG_DIR=$(CDPATH= cd -- "$PLUGIN_DIR/../../.." && pwd -P)
MOON_DIR="$CONFIG_DIR/base/moonraker"
TARGET="$MOON_DIR/components/$NAME.py"
FILE="$CONFIG_DIR/mod_data/plugins.moonraker.conf"

[ -f "$FILE" ] && sed -i "\|plugins/$NAME/$NAME\.moonraker\.conf|d" "$FILE"

if [ -L "$TARGET" ] &&
    [ "$(readlink "$TARGET")" = "../../../mod_data/plugins/$NAME/$NAME.py" ]; then
    rm "$TARGET"
fi

EXCLUDE="$MOON_DIR/.git/info/exclude"
[ -f "$EXCLUDE" ] && sed -i "\|^/components/$NAME\.py\$|d" "$EXCLUDE"

echo "notify_discord uninstalled"
echo "REBOOT" >/tmp/printer
