#!/bin/sh
# notify_discord - run by Zmod's ENABLE_PLUGIN name=notify_discord
#
# Links the Moonraker component into Zmod's Moonraker and includes the
# plugin's Moonraker settings. Zmod runs this on the host; Moonraker and
# its checkout live in Zmod's chroot, so the script reruns itself there.

[ -f /opt/config/mod/.shell/0.sh ] && . /opt/config/mod/.shell/0.sh
[ -f /usr/data/zmod/zmod/.shell/0.sh ] && . /usr/data/zmod/zmod/.shell/0.sh

set -eu

NAME=notify_discord
# /opt/config is the config folder both on the host and in the chroot.
CHROOT_PLUGIN_DIR="/opt/config/mod_data/plugins/$NAME"
PLUGIN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
CONFIG_DIR=$(CDPATH= cd -- "$PLUGIN_DIR/../../.." && pwd -P)

# Moonraker runs in Zmod's chroot (unless /ZMOD says there is none), so
# the work is done there.
if [ ! -f /ZMOD ] && [ -z "${NOTIFY_DISCORD_CHROOT:-}" ] &&
    [ -n "${MOD:-}" ] && [ -d "$MOD" ]; then
    unset LD_LIBRARY_PATH LD_PRELOAD
    exec chroot "$MOD" /bin/sh -c \
        "NOTIFY_DISCORD_CHROOT=1 $CHROOT_PLUGIN_DIR/install.sh"
fi

# Zmod 1.7+ keeps Moonraker in $DATA/zmod/moonraker, older ones in
# config/base/moonraker.
MOON_DIR=
for dir in ${DATA:+"$DATA/zmod/moonraker"} /usr/data/zmod/moonraker \
    /data/zmod/moonraker /root/printer_data/config/base/moonraker \
    "$CONFIG_DIR/base/moonraker"; do
    if [ -d "$dir/components" ]; then
        MOON_DIR=$dir
        break
    fi
done

if [ -z "$MOON_DIR" ]; then
    echo "notify_discord: Zmod's Moonraker not found" >&2
    exit 1
fi

TARGET="$MOON_DIR/components/$NAME.py"
INC="[include plugins/$NAME/$NAME.moonraker.conf]"
FILE="$CONFIG_DIR/mod_data/plugins.moonraker.conf"

if [ -e "$TARGET" ] && [ ! -L "$TARGET" ]; then
    echo "notify_discord: refusing to replace $TARGET" >&2
    exit 1
fi
ln -sfn "$CHROOT_PLUGIN_DIR/$NAME.py" "$TARGET"

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
