#!/bin/sh
# notify_discord - run by Zmod's ENABLE_PLUGIN name=notify_discord
#
# Links the Moonraker component into Zmod's Moonraker and includes the
# plugin's Moonraker settings. Paths are worked out from the plugin's own
# folder (mod_data/plugins/notify_discord), so the same script works on the
# AD5X (/usr/data/config) and AD5M (/data/config), on the host or in the
# chroot.

set -eu

NAME=notify_discord
PLUGIN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
CONFIG_DIR=$(CDPATH= cd -- "$PLUGIN_DIR/../../.." && pwd -P)
MOON_DIR="$CONFIG_DIR/base/moonraker"
TARGET="$MOON_DIR/components/$NAME.py"
# Relative, so it resolves both on the host and inside Moonraker's chroot.
LINK="../../../mod_data/plugins/$NAME/$NAME.py"
INC="[include plugins/$NAME/$NAME.moonraker.conf]"
FILE="$CONFIG_DIR/mod_data/plugins.moonraker.conf"

if [ ! -d "$MOON_DIR/components" ]; then
    echo "notify_discord: Zmod's Moonraker not found in $MOON_DIR" >&2
    exit 1
fi

if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
    echo "notify_discord: refusing to replace $TARGET" >&2
    exit 1
fi
ln -sfn "$LINK" "$TARGET"

# Keep Moonraker's update manager from reporting the link as an untracked
# source file in the moon repo.
EXCLUDE="$MOON_DIR/.git/info/exclude"
if [ -d "$MOON_DIR/.git" ]; then
    mkdir -p "$MOON_DIR/.git/info"
    touch "$EXCLUDE"
    grep -qxF "/components/$NAME.py" "$EXCLUDE" ||
        echo "/components/$NAME.py" >>"$EXCLUDE"
fi

touch "$FILE"
grep -qF "$INC" "$FILE" || echo "$INC" >>"$FILE"

if ! grep -q "plugins/notify/" "$FILE"; then
    echo "notify_discord: the notify plugin isn't enabled yet; run ENABLE_PLUGIN name=notify"
fi

echo "notify_discord installed"
echo "REBOOT" >/tmp/printer
