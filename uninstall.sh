#!/bin/sh
# notify_discord - run by Zmod's DISABLE_PLUGIN name=notify_discord
# Like install.sh, reruns itself in Zmod's chroot when Moonraker is only
# visible there.

[ -f /opt/config/mod/.shell/0.sh ] && . /opt/config/mod/.shell/0.sh

set -eu

NAME=notify_discord
CHROOT_PLUGIN_DIR="/opt/config/mod_data/plugins/$NAME"
PLUGIN_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
CONFIG_DIR=$(CDPATH= cd -- "$PLUGIN_DIR/../../.." && pwd -P)
FILE="$CONFIG_DIR/mod_data/plugins.moonraker.conf"

MOON_DIR=
for dir in /root/printer_data/config/base/moonraker "$CONFIG_DIR/base/moonraker"; do
    if [ -d "$dir/components" ]; then
        MOON_DIR=$dir
        break
    fi
done

if [ -z "$MOON_DIR" ] && [ -z "${NOTIFY_DISCORD_CHROOT:-}" ] &&
    [ -n "${MOD:-}" ] && [ -d "$MOD" ]; then
    unset LD_LIBRARY_PATH LD_PRELOAD
    exec chroot "$MOD" /bin/sh -c \
        "NOTIFY_DISCORD_CHROOT=1 $CHROOT_PLUGIN_DIR/uninstall.sh"
fi

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
