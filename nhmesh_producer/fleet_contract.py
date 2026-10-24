"""Shared mesh-fleet contract for Meshtastic (mirrors nhmesh-meshcore-gateway).

Routes (registered by WebInterface):
  GET  /api/nodes/<node>/config   normalised config
  PUT  /api/nodes/<node>/config   partial update of normalised keys
  GET  /api/nodes/<node>/status   reachable / last heard / metrics
  POST /api/nodes/<node>/ping     traceroute, waits for the reply

<node> is "self" (this producer's radio) or a node id ("!7c5ccbd0").

The local radio and a remote node expose the same meshtastic.node.Node object, so
read/write is ONE code path. Remote nodes only answer admin requests if this
gateway's public key is in their security.admin_key list; that failure is
reported as needs_admin_key rather than a generic error.

Normalised keys: region, modem_preset, tx_power, role, primary_channel, mqtt_address.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from meshtastic.protobuf import config_pb2

LORA = config_pb2.Config.LoRaConfig
DEVICE = config_pb2.Config.DeviceConfig
KEYS = ("region", "modem_preset", "tx_power", "role", "primary_channel", "mqtt_address")
REMOTE_TIMEOUT = 45.0


class NeedsAdminKey(Exception):
    """Remote node refused admin: our public key isn't in its admin_key list."""


def _with_timeout(fn: Callable[[], Any], timeout: float) -> Any:
    """Run a blocking meshtastic call with a hard timeout (the library can wait forever)."""
    box: dict[str, Any] = {}

    def run() -> None:
        try:
            box["value"] = fn()
        except Exception as e:  # surfaced below
            box["error"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"no response within {timeout:.0f}s")
    if "error" in box:
        err = box["error"]
        if "ADMIN_PUBLIC_KEY_UNAUTHORIZED" in str(err) or "unauthorized" in str(err).lower():
            raise NeedsAdminKey(str(err)) from err
        raise err
    return box.get("value")


def resolve(interface: Any, node: str) -> Any:
    """'self' -> local Node; otherwise a remote Node with its config fetched over the mesh."""
    if node == "self":
        return interface.localNode
    remote = interface.getNode(node, requestChannels=False)
    for section in ("lora", "device"):
        field = remote.localConfig.DESCRIPTOR.fields_by_name[section]
        _with_timeout(lambda f=field: remote.requestConfig(f), REMOTE_TIMEOUT)
    mqtt_field = remote.moduleConfig.DESCRIPTOR.fields_by_name["mqtt"]
    _with_timeout(lambda: remote.requestConfig(mqtt_field), REMOTE_TIMEOUT)
    _with_timeout(lambda: remote.requestChannels(), REMOTE_TIMEOUT)
    if not remote.localConfig.HasField("lora"):
        # The library swallows an admin NAK; an empty section after the wait means refused.
        raise NeedsAdminKey("remote returned no config (admin key not enrolled?)")
    return remote


def read_config(n: Any) -> dict[str, Any]:
    lora, device = n.localConfig.lora, n.localConfig.device
    primary = ""
    for ch in n.channels or []:
        if ch.index == 0 and ch.settings:
            primary = ch.settings.name
    return {
        "region": LORA.RegionCode.Name(lora.region),
        "modem_preset": LORA.ModemPreset.Name(lora.modem_preset),
        "tx_power": lora.tx_power,
        "role": DEVICE.Role.Name(device.role),
        "primary_channel": primary,
        "mqtt_address": n.moduleConfig.mqtt.address,
    }


def write_config(n: Any, update: dict[str, Any], timeout: float) -> dict[str, str]:
    """Apply normalised keys; one writeConfig per touched section. Returns key -> 'ok'."""
    unknown = set(update) - set(KEYS)
    if unknown:
        raise ValueError(f"unknown keys: {sorted(unknown)}")
    applied: dict[str, str] = {}
    lora, device = n.localConfig.lora, n.localConfig.device
    if "region" in update:
        lora.region = LORA.RegionCode.Value(update["region"])
    if "modem_preset" in update:
        lora.use_preset = True
        lora.modem_preset = LORA.ModemPreset.Value(update["modem_preset"])
    if "tx_power" in update:
        lora.tx_power = int(update["tx_power"])
    if {"region", "modem_preset", "tx_power"} & set(update):
        _with_timeout(lambda: n.writeConfig("lora"), timeout)
        applied.update({k: "ok" for k in ("region", "modem_preset", "tx_power") if k in update})
    if "role" in update:
        device.role = DEVICE.Role.Value(update["role"])
        _with_timeout(lambda: n.writeConfig("device"), timeout)
        applied["role"] = "ok"
    if "mqtt_address" in update:
        n.moduleConfig.mqtt.address = update["mqtt_address"]
        _with_timeout(lambda: n.writeConfig("mqtt"), timeout)
        applied["mqtt_address"] = "ok"
    if "primary_channel" in update:
        ch0 = next(ch for ch in n.channels if ch.index == 0)
        ch0.settings.name = update["primary_channel"]
        _with_timeout(lambda: n.writeChannel(0), timeout)
        applied["primary_channel"] = "ok"
    return applied


def node_status(interface: Any, node: str) -> dict[str, Any]:
    """Last-heard view from the local node DB (no RF round trip; use ping for that)."""
    my_id = (interface.getMyNodeInfo() or {}).get("user", {}).get("id")
    node_id = my_id if node == "self" else node
    entry = (interface.nodes or {}).get(node_id) or {}
    metrics = entry.get("deviceMetrics", {})
    return {
        "node_id": node_id,
        "last_heard": entry.get("lastHeard"),
        "snr": entry.get("snr"),
        "hops_away": entry.get("hopsAway"),
        "battery_level": metrics.get("batteryLevel"),
        "voltage": metrics.get("voltage"),
        "uptime_seconds": metrics.get("uptimeSeconds"),
    }


def ping(interface: Any, node: str, timeout: float = REMOTE_TIMEOUT) -> bool:
    """Traceroute and wait for the reply; True if it came back."""
    try:
        _with_timeout(lambda: interface.sendTraceRoute(dest=node, hopLimit=3), timeout)
        return True
    except (TimeoutError, Exception) as e:  # no reply = not reachable
        logging.info(f"[fleet] ping {node}: {e}")
        return False
