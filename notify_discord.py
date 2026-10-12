# notify_discord - Discord embeds for Zmod's notify plugin
#
# Zmod's notify plugin (https://github.com/ghzserg/notify) sends its
# messages through Moonraker's [notifier] sections, which hand them to
# Apprise. On Discord that gives plain text with the photo as an attachment.
#
# This component looks at notify's notifiers when Moonraker starts. Those
# whose URL is a Discord webhook post Discord embeds themselves, laid out like
# FlashForgeUI-Electron's (status, temps, progress bar, time, ETA, layer,
# file, photo inside the card). If posting fails, the message goes out through
# Apprise as before. Other services and other notifiers are left alone.
#
# install.sh links this file into Moonraker's components folder; the
# [notify_discord] section in notify_discord.moonraker.conf loads it.
#
# Copyright (C) 2026 DIEHARDave
# This file may be distributed under the terms of the GNU GPLv3 license.

from __future__ import annotations
import asyncio
import datetime
import functools
import json
import logging
import re
import uuid

from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ..confighelper import ConfigHelper
    from .klippy_apis import KlippyAPI
    from .notifier import Notifier, NotifierInstance
    from .http_client import HttpClient

# The notifiers in notify.moonraker.cfg; users' own notifiers are left alone.
NOTIFY_NOTIFIERS = (
    "print_start", "print_complete", "print_error", "print_cancelled",
    "print_paused", "print_resumed", "notifier", "notifier_photo",
)
DISCORD_RE = re.compile(
    r"^(?:https?://(?:(?:ptb|canary)\.)?discord(?:app)?\.com/api/webhooks/"
    r"|discord://(?:[^@/]*@)?)(?P<id>\d+)/(?P<token>[\w-]+)"
)
# Text of notify's _NOTIFY_ON_PERCENT: "file (5%) | 210.0/210.0°C | ...".
# The embed shows all of it, so it's left out of the card.
PROGRESS_RE = re.compile(
    r"^.* \(\d+%\) \| -?[\d.]+/[\d.]+°C \| -?[\d.]+/[\d.]+°C$")
# Seconds to wait before each attempt to reach Discord.
RETRY_DELAYS = (0., 10., 20., 30.)
# FlashForgeUI-Electron's status labels and embed colors.
STATUS_LABELS = {
    "Ready": "✅ Ready",
    "Printing": "🖨️ Printing",
    "Paused": "⏸️ Paused",
    "Completed": "✅ Completed",
    "Error": "❌ Error",
    "Cancelled": "🚫 Cancelled",
}
STATUS_COLORS = {"Printing": 0x00ff00, "Ready": 0x3498db, "Paused": 0xf39c12}
EVENT_STATUS = {
    "started": "Printing",
    "resumed": "Printing",
    "paused": "Paused",
    "error": "Error",
    "cancelled": "Cancelled",
}
KLIPPER_STATUS = {
    "printing": "Printing",
    "paused": "Paused",
    "error": "Error",
}


class NotifyDiscord:
    def __init__(self, config: ConfigHelper) -> None:
        self.server = config.get_server()
        self.enabled = config.getboolean("enabled", True)
        self.name_override = config.get("printer_name", "").strip()
        self.wrapped: List[str] = []
        self.server.register_remote_method(
            "notify_discord_status", self._handle_status)

    async def component_init(self) -> None:
        if not self.enabled:
            logging.info("notify_discord: turned off in [notify_discord]")
            return
        notifier: Optional[Notifier] = self.server.lookup_component(
            "notifier", None)
        if notifier is None:
            logging.info("notify_discord: Moonraker's notifier isn't loaded")
            return
        for name, inst in notifier.notifiers.items():
            match = DISCORD_RE.match(getattr(inst, "url", "") or "")
            if name not in NOTIFY_NOTIFIERS or match is None:
                continue
            webhook = "https://discord.com/api/webhooks/%s/%s" % (
                match.group("id"), match.group("token"))
            # Moonraker calls inst.notify(event_name, event_args, message)
            # for both print events and _NOTIFY.
            inst.notify = functools.partial(
                self._notify_discord, inst, webhook, inst.notify)
            self.wrapped.append(name)
        if self.wrapped:
            logging.info(
                "notify_discord: Discord embeds for " + ", ".join(self.wrapped))

    def _handle_status(self) -> None:
        if not self.enabled:
            msg = "turned off ([notify_discord] enabled: False)"
        elif self.wrapped:
            msg = "Discord embeds are on for " + ", ".join(self.wrapped)
        elif self.server.lookup_component("notifier", None) is None:
            msg = "the notify plugin isn't enabled (ENABLE_PLUGIN name=notify)"
        else:
            msg = ("notify's url isn't a Discord webhook, so messages are "
                   "sent as usual")
        self.server.send_event(
            "server:gcode_response", f"// notify_discord: {msg}")

    async def _notify_discord(
        self,
        inst: NotifierInstance,
        webhook: str,
        fallback: Callable,
        event_name: str,
        event_args: List,
        message: str = "",
    ) -> None:
        try:
            embed, photo = await self._build_embed(
                inst, event_name, event_args, message)
            await self._post_discord(webhook, embed, photo)
        except Exception:
            logging.exception(
                "notify_discord: Discord embed failed, sending plain text")
            await fallback(event_name, event_args, message)

    async def _build_embed(
        self,
        inst: NotifierInstance,
        event_name: str,
        event_args: List,
        message: str,
    ):
        kapis: KlippyAPI = self.server.lookup_component("klippy_apis")
        status = await kapis.query_objects({
            "print_stats": None,
            "display_status": ["progress"],
            "virtual_sdcard": ["progress"],
            "extruder": ["temperature", "target"],
            "heater_bed": ["temperature", "target"],
            "gcode_move": ["gcode_position"],
        }, default={})
        stats = dict(status.get("print_stats", {}))
        # Print events carry print_stats as it was when the event fired.
        if len(event_args) > 1 and isinstance(event_args[1], dict):
            stats.update(event_args[1])
        message = (message or "").strip()
        if event_name == "complete":
            embed = self._complete_embed(stats)
        else:
            if PROGRESS_RE.match(message):
                message = ""
            if event_name == "error" and not message:
                message = stats.get("message", "")
            embed = self._status_embed(event_name, stats, status, message)
        photo = await self._snapshot(inst, event_name, event_args, message)
        if photo is not None:
            embed["image"] = {"url": "attachment://snapshot.jpg"}
        return embed, photo

    # Right after boot the printer's clock is wrong until it syncs, so HTTPS
    # fails ("certificate is not yet valid"); Discord can also have a bad
    # moment. Both are retried for about a minute. Discord refusing the
    # card (4xx) isn't.
    async def _post_discord(
        self, webhook: str, embed: Dict[str, Any], photo: Optional[bytes]
    ) -> None:
        client: HttpClient = self.server.lookup_component("http_client")
        for delay in RETRY_DELAYS:
            if delay:
                await asyncio.sleep(delay)
            # Set per attempt, so a retry after the clock syncs gets the
            # right time.
            embed["timestamp"] = datetime.datetime.now(
                datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            if photo is None:
                body: Any = json.dumps({"embeds": [embed]})
                headers = {"Content-Type": "application/json"}
            else:
                body, headers = _multipart({"embeds": [embed]}, photo)
            resp = await client.request(
                "POST", webhook, body, headers, request_timeout=15.)
            if resp.status_code in (200, 204):
                return
            if resp.status_code < 500:
                break
            logging.info(
                f"notify_discord: Discord unreachable ({resp.status_code}), "
                "retrying")
        raise RuntimeError(
            f"Discord returned {resp.status_code}: {resp.text[:200]}")

    def _printer_name(self) -> str:
        if self.name_override:
            return self.name_override
        name = ""
        secrets = self.server.lookup_component("secrets", None)
        if secrets is not None:
            section = secrets.get("notify", {})
            if isinstance(section, dict):
                name = str(section.get("name", "")).strip()
        if not name or "{" in name:
            return "Flashforge Printer"
        return name

    def _status_embed(
        self,
        event_name: str,
        stats: Dict[str, Any],
        status: Dict[str, Any],
        message: str,
    ) -> Dict[str, Any]:
        state = stats.get("state", "")
        label = EVENT_STATUS.get(event_name) or KLIPPER_STATUS.get(
            state, "Ready")
        fields: List[Dict[str, Any]] = [{
            "name": "Status",
            "value": STATUS_LABELS.get(label, label),
            "inline": True,
        }]
        for key, title in (("extruder", "Extruder Temp"),
                           ("heater_bed", "Bed Temp")):
            heater = status.get(key)
            if heater:
                fields.append({
                    "name": title,
                    "value": "%.2f°C / %.2f°C" % (
                        heater.get("temperature", 0.),
                        heater.get("target", 0.)),
                    "inline": True,
                })
        if label in ("Printing", "Paused") and stats.get("filename"):
            fields.extend(self._job_fields(stats, status))
        embed: Dict[str, Any] = {
            "title": f"🖨️ {self._printer_name()}",
            "color": STATUS_COLORS.get(label, 0x95a5a6),
            "fields": fields,
        }
        if message:
            embed["description"] = message[:4000]
        return embed

    def _job_fields(
        self, stats: Dict[str, Any], status: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        filename = stats.get("filename", "")
        meta = self._metadata(filename)
        # M73 progress from the slicer is time based; the file position is
        # the fallback.
        progress = float(
            status.get("display_status", {}).get("progress") or
            status.get("virtual_sdcard", {}).get("progress") or 0.)
        progress = min(max(progress, 0.), 1.)
        filled = int(progress * 100 // 10)
        fields = [{
            "name": "Progress",
            "value": "%s %d%%" % ("█" * filled + "░" * (10 - filled),
                                  round(progress * 100)),
            "inline": False,
        }]
        elapsed = float(stats.get("print_duration") or 0.)
        fields.append({
            "name": "Print Time",
            "value": _duration(elapsed),
            "inline": True,
        })
        estimate = float(meta.get("estimated_time") or 0.)
        remaining = None
        if estimate > 0:
            remaining = estimate * (1. - progress)
        elif progress > .01:
            remaining = elapsed / progress - elapsed
        if remaining is not None:
            # Discord shows <t:...> in each reader's own time zone, so the
            # printer's clock zone doesn't matter.
            eta = int(datetime.datetime.now(
                datetime.timezone.utc).timestamp() + remaining)
            fields.append({
                "name": "ETA",
                "value": f"<t:{eta}:t>",
                "inline": True,
            })
        layer = self._layer(stats, status, meta)
        if layer is not None:
            fields.append({
                "name": "Layer",
                "value": "%d / %d" % layer,
                "inline": True,
            })
        fields.append({"name": "File", "value": filename, "inline": False})
        return fields

    def _complete_embed(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        duration = float(stats.get("total_duration") or 0.)
        return {
            "title": "✅ Print Complete!",
            "color": 0x00ff00,
            "fields": [
                {"name": "File", "value": stats.get("filename") or "Unknown",
                 "inline": False},
                {"name": "Total Time",
                 "value": _duration(duration) if duration else "Unknown",
                 "inline": True},
            ],
            "footer": {"text": self._printer_name()},
        }

    def _metadata(self, filename: str) -> Dict[str, Any]:
        if not filename:
            return {}
        try:
            fm = self.server.lookup_component("file_manager")
            return fm.get_file_metadata(filename) or {}
        except Exception:
            return {}

    # print_stats.info has the layer when the slicer emits
    # SET_PRINT_STATS_INFO; otherwise it's worked out from the nozzle height
    # and the file's layer height.
    def _layer(
        self,
        stats: Dict[str, Any],
        status: Dict[str, Any],
        meta: Dict[str, Any],
    ):
        info = stats.get("info") or {}
        if info.get("current_layer") and info.get("total_layer"):
            return int(info["current_layer"]), int(info["total_layer"])
        total = int(meta.get("layer_count") or 0)
        height = float(meta.get("layer_height") or 0.)
        first = float(meta.get("first_layer_height") or height)
        pos = status.get("gcode_move", {}).get("gcode_position") or []
        if total <= 0 or height <= 0. or len(pos) < 3:
            return None
        layer = int(round((float(pos[2]) - first) / height)) + 1
        return min(max(layer, 1), total), total

    async def _snapshot(
        self,
        inst: NotifierInstance,
        event_name: str,
        event_args: List,
        message: str,
    ) -> Optional[bytes]:
        if inst.attach is None:
            return None
        try:
            rendered = inst.attach.render({
                "event_name": event_name,
                "event_args": event_args,
                "event_message": message,
            })
        except Exception:
            return None
        urls = [u.strip() for u in rendered.splitlines()
                if re.match(r"https?://", u.strip())]
        if not urls:
            return None
        client: HttpClient = self.server.lookup_component("http_client")
        resp = await client.request(
            "GET", urls[0], request_timeout=5., enable_cache=False)
        if resp.has_error() or resp.status_code != 200 or not resp.content:
            logging.info(f"notify_discord: no snapshot from {urls[0]}")
            return None
        return resp.content


def _duration(seconds: float) -> str:
    seconds = int(seconds)
    return "%dh %dm" % (seconds // 3600, seconds % 3600 // 60)


def _multipart(payload: Dict[str, Any], photo: bytes):
    boundary = uuid.uuid4().hex
    body = b"".join([
        b"--%s\r\n" % boundary.encode(),
        b'Content-Disposition: form-data; name="payload_json"\r\n',
        b"Content-Type: application/json\r\n\r\n",
        json.dumps(payload).encode(), b"\r\n",
        b"--%s\r\n" % boundary.encode(),
        b'Content-Disposition: form-data; name="files[0]"; '
        b'filename="snapshot.jpg"\r\n',
        b"Content-Type: image/jpeg\r\n\r\n",
        photo, b"\r\n",
        b"--%s--\r\n" % boundary.encode(),
    ])
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    return body, headers


def load_component(config: ConfigHelper) -> NotifyDiscord:
    return NotifyDiscord(config)
