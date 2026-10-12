# notify_discord

Discord cards for the [Zmod notify plugin](https://github.com/ghzserg/notify) on Flashforge AD5X, AD5M and AD5M Pro printers.

notify sends its messages through Moonraker and Apprise. On Discord, that shows up as a line of plain text with the camera photo attached as a file. With this plugin installed, the same messages arrive as Discord embeds laid out like [FlashForgeUI](https://github.com/Parallel-7/FlashForgeUI-Electron)'s:

- a colored card with the printer's name, status, and nozzle and bed temperatures
- while printing: a progress bar, print time, ETA, layer and file name
- the camera photo inside the card
- a "✅ Print Complete!" card with the total time when a print finishes
- Zmod's own messages (printer on, filament runout, `_NOTIFY` text from your G-code) at the top of the card

The plugin only changes how messages look. Which messages are sent, and when, is still set by notify. If notify's `url` isn't a Discord webhook, nothing changes. If Discord rejects a card, the message is sent as plain text as before.

## Requirements

- [Zmod](https://github.com/ghzserg/zmod)
- The notify plugin, enabled and working (`ENABLE_PLUGIN name=notify`), with a Discord webhook as its `url`. See [Discord webhook](#discord-webhook).

## Installation

1. Add this to `mod_data/user.moonraker.conf`:

   ```ini
   [update_manager notify_discord]
   type: git_repo
   channel: stable
   path: /root/printer_data/config/mod_data/plugins/notify_discord
   origin: https://github.com/DIEHARDave/notify_discord.git
   is_system_service: False
   primary_branch: main
   ```

2. In the Mainsail or Fluidd console, run:

   ```
   ENABLE_PLUGIN name=notify_discord
   ```

   The printer reboots.

3. Check it with:

   ```
   NOTIFY_DISCORD_STATUS
   ```

   It should answer `Discord embeds are on for print_start, print_complete, …`. Then send a test card with `_NOTIFY MSG=Test`.

## Removal

```
DISABLE_PLUGIN name=notify_discord
```

notify goes back to plain text after the reboot.

## Discord webhook

In your Discord server, open the channel's settings → Integrations → Webhooks → New Webhook, then **Copy Webhook URL**. In `mod_data/notify.txt`, paste it as `url` unchanged:

```ini
[notify]
url: https://discord.com/api/webhooks/123456789012345678/abcdefghijklmnopqrstuvwxyz
name: My AD5X
```

Then run `UPDATE_NOTIFY`. Apprise's `discord://webhook_id/webhook_token` form works too.

`name` becomes the card title.

## Settings

To change a setting, add a `[notify_discord]` section to `mod_data/user.moonraker.conf` and restart Moonraker:

```ini
[notify_discord]
# Plain text again, without disabling the plugin
enabled: False
# Card title, instead of the name from notify.txt
printer_name: My AD5X
```

The photo, the progress interval and the on/off switches for each message are notify's settings (`notify_photo`, `notify_percent`, `notify_on`, and so on). See the [notify README](https://github.com/ghzserg/notify#configuration).

## Notes

- The ETA uses the slicer's time estimate and shows in each reader's own time zone.
- The layer comes from the slicer's `SET_PRINT_STATS_INFO`. Without it, the layer is worked out from the nozzle height and the file's layer height.
- The `body:` text of notify's notifiers isn't used for cards, so changes to it only show up on other services.
- The plugin links `notify_discord.py` into the `components` folder of Zmod's Moonraker (inside Zmod's chroot). If Moonraker is ever reinstalled from scratch, run `ENABLE_PLUGIN name=notify_discord` again.

## How it works

At startup, the Moonraker component looks through notify's notifiers (`print_start`, `print_complete`, `print_error`, `print_cancelled`, `print_paused`, `print_resumed`, `notifier`, `notifier_photo`). For each one whose URL is a Discord webhook, it builds the card from Klipper's status and the file's metadata, takes the photo from the notifier's `attach:` URL, and posts both to the webhook. Your own `[notifier]` sections are left alone.

The card layout comes from [FLSUN_notify](https://github.com/DIEHARDave/FLSUN_notify), the FLSun T1 Pro port of notify.

## License

GPLv3, like notify and Zmod.
