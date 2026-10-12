#!/bin/sh
# notify_discord - run by Zmod's DISABLE_PLUGIN name=notify_discord
# Like install.sh, does its work inside Zmod's chroot.

[ -f /opt/config/mod/.shell/0.sh ] && . /opt/config/mod/.shell/0.sh
[ -f /usr/data/zmod/zmod/.shell/0.sh ] && . /usr/data/zmod/zmod/.shell/0.sh

set -eu

NAME=notify_discord
CHROOT_PLUGIN_DIR="/opt/config/mod_data/plugins/$NAME"
PLUGIN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
CONFIG_DIR=$(CDPATH= cd -- "$PLUGIN_DIR/../../.." && pwd -P)
FILE="$CONFIG_DIR/mod_data/plugins.moonraker.conf"

# Moonraker runs in Zmod's chroot (unless /ZMOD says there is none), so
# the work is done there.
if [ ! -f /ZMOD ] && [ -z "${NOTIFY_DISCORD_CHROOT:-}" ] &&
    [ -n "${MOD:-}" ] && [ -d "$MOD" ]; then
    unset LD_LIBRARY_PATH LD_PRELOAD
    exec chroot "$MOD" /bin/sh -c \
        "NOTIFY_DISCORD_CHROOT=1 $CHROOT_PLUGIN_DIR/uninstall.sh"
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

[ -f "$FILE" ] && sed -i "\|plugins/$NAME/$NAME\.moonraker\.conf|d" "$FILE"

if [ -n "$MOON_DIR" ]; then
    TARGET="$MOON_DIR/components/$NAME.py"
    if [ -L "$TARGET" ]; then
        case "$(readlink "$TARGET")" in
            "$CHROOT_PLUGIN_DIR/$NAME.py" | "../../../mod_data/plugins/$NAME/$NAME.py")
                rm "$TARGET" ;;
        esac
    fi
    EXCLUDE="$MOON_DIR/.git/info/exclude"
    [ -f "$EXCLUDE" ] && sed -i "\|^/components/$NAME\.py\$|d" "$EXCLUDE"
fi

echo "notify_discord uninstalled"
echo "REBOOT" >/tmp/printer
