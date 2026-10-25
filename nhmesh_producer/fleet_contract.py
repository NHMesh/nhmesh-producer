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
import time
from collections.abc import Callable
from typing import Any

from meshtastic.protobuf import config_pb2, portnums_pb2, telemetry_pb2

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


# Remote device telemetry. Many nodes never broadcast it (the tree LF node sent none in
# 8 h on 2026-10-25), so the node DB's deviceMetrics can be any age and carry no
# timestamp. A telemetry REQUEST needs no admin key; it's asked at most hourly per node,
# and only of nodes heard recently, so a dead site costs no airtime.
TELEMETRY_EVERY = 3600.0
TELEMETRY_IF_HEARD_WITHIN = 6 * 3600.0
_telemetry: dict[str, dict[str, Any]] = {}  # node id -> {"at", "metrics"} or {"at", "error"}
_telemetry_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _node_lock(node: str) -> threading.Lock:
    # Per node: one node's 45 s request must not stall status calls for the others.
    with _locks_guard:
        return _telemetry_locks.setdefault(node, threading.Lock())


def request_telemetry(interface: Any, node: str, timeout: float = REMOTE_TIMEOUT) -> dict[str, Any]:
    """Ask a remote node for its device metrics and wait for the reply (camelCase keys)."""
    got: dict[str, Any] = {}
    done = threading.Event()

    def on_response(packet: dict[str, Any]) -> None:
        decoded = packet.get("decoded", {})
        metrics = (decoded.get("telemetry") or {}).get("deviceMetrics")
        if metrics is not None:  # a routing NAK also lands here; keep waiting for metrics
            got.update(metrics)
            done.set()

    req = telemetry_pb2.Telemetry()
    req.device_metrics.CopyFrom(telemetry_pb2.DeviceMetrics())
    interface.sendData(req, destinationId=node, portNum=portnums_pb2.PortNum.TELEMETRY_APP,
                       wantResponse=True, onResponse=on_response, channelIndex=0)
    if not done.wait(timeout):
        raise TimeoutError(f"no telemetry from {node} within {timeout:.0f}s")
    return got


def _fresh_telemetry(interface: Any, node: str, last_heard: float | None, now: float) -> dict[str, Any] | None:
    with _node_lock(node):
        cached = _telemetry.get(node)
        due = cached is None or now - cached["at"] >= TELEMETRY_EVERY
        heard = last_heard is not None and now - last_heard <= TELEMETRY_IF_HEARD_WITHIN
        if not (due and heard):
            return cached
        try:
            entry = {"at": now, "metrics": request_telemetry(interface, node)}
        except Exception as e:  # cached too, so a silent node isn't re-asked every poll
            logging.info(f"[fleet] telemetry {node}: {e}")
            entry = {"at": now, "error": str(e)}
        _telemetry[node] = entry
        return entry


def node_status(interface: Any, node: str, now: Callable[[], float] = time.time) -> dict[str, Any]:
    """Last-heard view from the local node DB, plus hourly-requested telemetry for remote nodes.

    telemetry_time is when voltage/battery were actually measured: the request time for a
    remote node, None when only an undated node-DB value exists.
    """
    my_id = (interface.getMyNodeInfo() or {}).get("user", {}).get("id")
    node_id = my_id if node == "self" else node
    entry = (interface.nodes or {}).get(node_id) or {}
    metrics = dict(entry.get("deviceMetrics", {}))
    telemetry_time = entry.get("lastHeard") if node == "self" else None  # own radio: local
    if node != "self":
        t = _fresh_telemetry(interface, node_id, entry.get("lastHeard"), now())
        if t and "metrics" in t:
            metrics.update(t["metrics"])
            telemetry_time = int(t["at"])
    return {
        "node_id": node_id,
        "last_heard": entry.get("lastHeard"),
        "snr": entry.get("snr"),
        "hops_away": entry.get("hopsAway"),
        "battery_level": metrics.get("batteryLevel"),
        "voltage": metrics.get("voltage"),
        "uptime_seconds": metrics.get("uptimeSeconds"),
        "telemetry_time": telemetry_time,
    }


def ping(interface: Any, node: str, timeout: float = REMOTE_TIMEOUT) -> bool:
    """Traceroute and wait for the reply; True if it came back."""
    try:
        _with_timeout(lambda: interface.sendTraceRoute(dest=node, hopLimit=3), timeout)
        return True
    except (TimeoutError, Exception) as e:  # no reply = not reachable
        logging.info(f"[fleet] ping {node}: {e}")
        return False
