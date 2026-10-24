"""
API-only interface for nhmesh-producer.
"""

import hmac
import logging
import os
import threading
import time
from typing import Any

from flask import Flask, jsonify, request

from nhmesh_producer import fleet_contract as fc

# Bearer token for every route except the healthcheck. The API includes remote
# admin (reboot/shutdown/factory-reset/config of mesh nodes), so once it is
# reachable beyond the container it must not be open. Unset = open (logged).
API_TOKEN = os.environ.get("API_TOKEN", "")
OPEN_PATHS = frozenset({"/api/health"})


class WebInterface:
    """API-only interface for monitoring and controlling nhmesh-producer"""

    def __init__(self, handler: Any, host: str = "0.0.0.0", port: int = 5001):
        self.handler = handler
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.start_time = time.time()
        self.packets_published = 0
        self.last_packet_time: float | None = None
        self.server_thread: threading.Thread | None = None

        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup Flask API routes"""
        if not API_TOKEN:
            logging.warning("API_TOKEN not set: producer API (incl. remote admin) is UNAUTHENTICATED")

        @self.app.before_request
        def require_token():
            if API_TOKEN and request.path not in OPEN_PATHS:
                supplied = request.headers.get("Authorization", "")
                if not hmac.compare_digest(supplied.encode(), f"Bearer {API_TOKEN}".encode()):
                    return jsonify({"detail": "unauthorized"}), 401
            return None

        self._setup_fleet_routes()

        @self.app.route("/api/stats")
        def stats():
            """Stats API endpoint for health checks"""
            health_status = self.handler.connection_manager.get_health_status()
            connection_info = self.handler.connection_manager.get_connection_info()

            return jsonify(
                {
                    "status": "healthy"
                    if health_status.get("connected")
                    else "unhealthy",
                    "uptime_seconds": int(time.time() - self.start_time),
                    "meshtastic": {
                        "connected": health_status.get("connected", False),
                        "connection_type": connection_info.get("connection_type"),
                        "node_ip": connection_info.get("node_ip"),
                        "serial_port": connection_info.get("serial_port"),
                        "connected_node_id": connection_info.get("connected_node_id"),
                        "connection_errors": health_status.get("connection_errors", 0),
                        "time_since_last_packet": health_status.get(
                            "time_since_last_packet"
                        ),
                        "reconnecting": health_status.get("reconnecting", False),
                    },
                    "mqtt": {
                        "connected": getattr(self.handler, "mqtt_connected", False),
                        "broker": self.handler.broker,
                        "port": self.handler.port,
                        "topic": self.handler.topic,
                    },
                    "packets": {
                        "published": self.packets_published,
                        "last_packet_time": self.last_packet_time,
                    },
                    "health_monitor": {
                        "alive": health_status.get("health_monitor_alive", False),
                        "check_interval": health_status.get("health_check_interval"),
                        "in_progress": health_status.get("health_check_in_progress", False),
                    },
                }
            )

        @self.app.route("/api/health")
        def health():
            """Health check (Docker healthcheck compatible): radio AND broker."""
            mesh_ok = self.handler.connection_manager.is_connected()
            mqtt_ok = bool(getattr(self.handler, "mqtt_connected", False))
            body = {
                "status": "healthy" if (mesh_ok and mqtt_ok) else "unhealthy",
                "timestamp": time.time(),
                "meshtastic_connected": mesh_ok,
                "mqtt_connected": mqtt_ok,
            }
            if not mesh_ok:
                body["reason"] = "Meshtastic not connected"
            elif not mqtt_ok:
                body["reason"] = "MQTT broker not connected"
            return jsonify(body), (200 if mesh_ok and mqtt_ok else 503)

        @self.app.route("/api/connection")
        def connection():
            """Detailed connection information endpoint"""
            return jsonify(self.handler.connection_manager.get_connection_info())

        @self.app.route("/api/message", methods=["POST"])
        def send_message():
            """Send a text message via Meshtastic.

            JSON body: {"text": "...", "channel": 0, "to": "!hexid"}
            Response matches MeshCore gateway format.
            """
            from flask import request

            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "JSON body required"}), 400

            text = data.get("text", "")
            if not text:
                return jsonify({"error": "'text' field required"}), 400

            channel_index = int(data.get("channel", 0))
            destination_id = data.get("to") or None

            result = self.handler.send_text(
                text=text,
                channel_index=channel_index,
                destination_id=destination_id,
            )

            # Normalize to MeshCore format: {channel, text, result_type}
            channel_name = result.get("channel", f"ch{channel_index}")
            response = {
                "channel": channel_name,
                "text": text,
                "result_type": "OK" if result.get("status") == "sent" else "ERROR",
            }
            if result.get("status") != "sent":
                response["error"] = result.get("error", "unknown")

            status_code = 200 if result.get("status") == "sent" else 500
            return jsonify(response), status_code

        @self.app.route("/api/device")
        def device_info():
            """Device info — normalized to match MeshCore gateway /api/device format."""
            interface = self.handler.connection_manager.get_interface()
            if not interface:
                return jsonify({"error": "No Meshtastic interface"}), 503

            try:
                my_info = interface.getMyNodeInfo() or {}
                user = my_info.get("user", {}) if isinstance(my_info, dict) else {}
                position = my_info.get("position", {}) if isinstance(my_info, dict) else {}
                device_metrics = my_info.get("deviceMetrics", {}) if isinstance(my_info, dict) else {}

                def safe_get(obj, key, default=None):
                    if isinstance(obj, dict):
                        return obj.get(key, default)
                    return getattr(obj, key, default)

                fw_version = "unknown"
                try:
                    if hasattr(interface, "metadata") and interface.metadata:
                        fw_version = getattr(interface.metadata, "firmware_version", "unknown")
                except Exception:
                    pass

                # Normalized structure matching MeshCore: device_info + self_info
                return jsonify({
                    "protocol": "meshtastic",
                    "device_info": {
                        "model": safe_get(user, "hwModel", "Unknown"),
                        "ver": fw_version,
                        "mac_address": safe_get(user, "macaddr"),
                        "connection_type": self.handler.connection_type,
                        "modem_preset": self.handler.modem_preset,
                        "channel_num": self.handler.channel_num,
                        "battery_level": safe_get(device_metrics, "batteryLevel") if device_metrics else None,
                        "voltage": safe_get(device_metrics, "voltage") if device_metrics else None,
                    },
                    "self_info": {
                        "name": safe_get(user, "longName", "Unknown"),
                        "short_name": safe_get(user, "shortName"),
                        "node_id": safe_get(user, "id"),
                        "adv_lat": safe_get(position, "latitude") if position else None,
                        "adv_lon": safe_get(position, "longitude") if position else None,
                        "altitude": safe_get(position, "altitude") if position else None,
                    },
                    "uptime_seconds": int(time.time() - self.start_time),
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/channels")
        def channels():
            """Channel list — flat array matching MeshCore gateway /api/channels format."""
            interface = self.handler.connection_manager.get_interface()
            if not interface:
                return jsonify({"error": "No Meshtastic interface"}), 503

            try:
                channel_list = []
                if interface.localNode and interface.localNode.channels:
                    for ch in interface.localNode.channels:
                        if hasattr(ch, "settings") and ch.settings:
                            role_val = ch.role if hasattr(ch, "role") else 0
                            role_name = {0: "DISABLED", 1: "PRIMARY", 2: "SECONDARY"}.get(role_val, str(role_val))
                            channel_list.append({
                                "index": ch.index,
                                "name": ch.settings.name or (
                                    self.handler.modem_preset if ch.index == 0 else f"ch{ch.index}"
                                ),
                                "has_secret": bool(ch.settings.psk) and len(ch.settings.psk) > 0,
                                "role": role_name,
                            })

                # Return flat array like MeshCore gateway
                return jsonify(channel_list)
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/nodes")
        def nodes():
            """Mesh node database from the connected radio."""
            interface = self.handler.connection_manager.get_interface()
            if not interface:
                return jsonify({"error": "No Meshtastic interface"}), 503

            try:
                node_list = []
                nodes_dict = interface.nodes or {}
                for node_id, node_data in nodes_dict.items():
                    user = node_data.get("user", {})
                    position = node_data.get("position", {})
                    snr = node_data.get("snr")
                    last_heard = node_data.get("lastHeard")

                    node_list.append({
                        "id": user.get("id", node_id),
                        "long_name": user.get("longName"),
                        "short_name": user.get("shortName"),
                        "hardware_model": user.get("hwModel"),
                        "snr": snr,
                        "last_heard": last_heard,
                        "position": {
                            "latitude": position.get("latitude"),
                            "longitude": position.get("longitude"),
                            "altitude": position.get("altitude"),
                        } if position else None,
                        "hops_away": node_data.get("hopsAway"),
                    })

                # Sort by last_heard descending (most recent first)
                node_list.sort(
                    key=lambda n: n.get("last_heard") or 0,
                    reverse=True,
                )

                return jsonify({
                    "node_count": len(node_list),
                    "nodes": node_list,
                })
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        # --- Remote Admin Endpoints ---
        # These use interface.getNode(nodeId) to send admin messages over the mesh.

        def _get_remote_node(node_id: str):
            """Helper: get interface and remote Node object, or raise."""
            interface = self.handler.connection_manager.get_interface()
            if not interface:
                return None, None
            if node_id == "self":  # shared contract: "self" = this producer's radio
                return interface, interface.localNode
            try:
                node = interface.getNode(node_id, requestChannels=False)
                return interface, node
            except Exception as e:
                logging.error(f"Failed to get remote node {node_id}: {e}")
                return interface, None

        @self.app.route("/api/nodes/<node_id>/reboot", methods=["POST"])
        def reboot_node(node_id):
            """Reboot a remote node over the mesh admin channel."""
            interface, node = _get_remote_node(node_id)
            if not interface:
                return jsonify({"error": "No Meshtastic interface"}), 503
            if not node:
                return jsonify({"error": f"Node {node_id} not found"}), 404

            try:
                node.reboot()
                return jsonify({
                    "result_type": "OK",
                    "node": node_id,
                    "action": "reboot",
                })
            except Exception as e:
                return jsonify({"result_type": "ERROR", "error": str(e)}), 500

        @self.app.route("/api/nodes/<node_id>/shutdown", methods=["POST"])
        def shutdown_node(node_id):
            """Shutdown a remote node over the mesh admin channel."""
            interface, node = _get_remote_node(node_id)
            if not interface:
                return jsonify({"error": "No Meshtastic interface"}), 503
            if not node:
                return jsonify({"error": f"Node {node_id} not found"}), 404

            try:
                node.shutdown()
                return jsonify({
                    "result_type": "OK",
                    "node": node_id,
                    "action": "shutdown",
                })
            except Exception as e:
                return jsonify({"result_type": "ERROR", "error": str(e)}), 500

        @self.app.route("/api/nodes/<node_id>/metadata")
        def node_metadata(node_id):
            """Get firmware/hardware metadata from a remote node."""
            interface, node = _get_remote_node(node_id)
            if not interface:
                return jsonify({"error": "No Meshtastic interface"}), 503
            if not node:
                return jsonify({"error": f"Node {node_id} not found"}), 404

            try:
                metadata = node.getMetadata()
                if metadata:
                    return jsonify({
                        "node": node_id,
                        "firmware_version": getattr(metadata, "firmware_version", None),
                        "device_state_version": getattr(metadata, "device_state_version", None),
                        "canShutdown": getattr(metadata, "canShutdown", None),
                        "hasWifi": getattr(metadata, "hasWifi", None),
                        "hasBluetooth": getattr(metadata, "hasBluetooth", None),
                        "hasEthernet": getattr(metadata, "hasEthernet", None),
                        "role": getattr(metadata, "role", None),
                        "hw_model": getattr(metadata, "hw_model", None),
                    })
                return jsonify({"node": node_id, "metadata": None})
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @self.app.route("/api/nodes/<node_id>/factory-reset", methods=["POST"])
        def factory_reset_node(node_id):
            """Factory reset a remote node. DESTRUCTIVE — erases all config."""
            interface, node = _get_remote_node(node_id)
            if not interface:
                return jsonify({"error": "No Meshtastic interface"}), 503
            if not node:
                return jsonify({"error": f"Node {node_id} not found"}), 404

            try:
                node.factoryReset()
                return jsonify({
                    "result_type": "OK",
                    "node": node_id,
                    "action": "factory_reset",
                })
            except Exception as e:
                return jsonify({"result_type": "ERROR", "error": str(e)}), 500

        @self.app.route("/api/nodes/<node_id>/position", methods=["POST"])
        def set_node_position(node_id):
            """Set fixed position on a remote node."""
            from flask import request

            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "JSON body required"}), 400

            lat = data.get("latitude")
            lon = data.get("longitude")
            alt = data.get("altitude", 0)

            if lat is None or lon is None:
                return jsonify({"error": "latitude and longitude required"}), 400

            interface, node = _get_remote_node(node_id)
            if not interface:
                return jsonify({"error": "No Meshtastic interface"}), 503
            if not node:
                return jsonify({"error": f"Node {node_id} not found"}), 404

            try:
                node.setFixedPosition(lat, lon, alt)
                return jsonify({
                    "result_type": "OK",
                    "node": node_id,
                    "action": "set_position",
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": alt,
                })
            except Exception as e:
                return jsonify({"result_type": "ERROR", "error": str(e)}), 500

    def increment_packet_count(self) -> None:
        """Increment the packet counter (call this when packet is published)"""
        self.packets_published += 1
        self.last_packet_time = time.time()

    def _setup_fleet_routes(self) -> None:
        """Shared mesh-fleet contract (same paths/keys as nhmesh-meshcore-gateway)."""

        def iface_or_503():
            interface = self.handler.connection_manager.get_interface()
            if not interface:
                return None, (jsonify({"error": "No Meshtastic interface"}), 503)
            return interface, None

        def envelope(node: str, action: str, **kw):
            return jsonify({"result_type": kw.pop("result_type", "OK"), "node": node, "action": action, **kw})

        @self.app.route("/api/nodes/<node>/config", methods=["GET"])
        def fleet_get_config(node):
            interface, err = iface_or_503()
            if err:
                return err
            try:
                n = fc.resolve(interface, node)
                return envelope(node, "get_config", config=fc.read_config(n))
            except fc.NeedsAdminKey as e:
                return envelope(node, "get_config", result_type="NEEDS_ADMIN_KEY", error=str(e)), 403
            except TimeoutError as e:
                return envelope(node, "get_config", result_type="TIMEOUT", error=str(e)), 504

        @self.app.route("/api/nodes/<node>/config", methods=["PUT"])
        def fleet_set_config(node):
            interface, err = iface_or_503()
            if err:
                return err
            update = request.get_json(silent=True) or {}
            try:
                n = fc.resolve(interface, node)
                applied = fc.write_config(n, update, fc.REMOTE_TIMEOUT)
                # region/preset changes make the radio reboot itself
                reboot = bool({"region", "modem_preset"} & set(update))
                return envelope(node, "set_config", applied=applied, reboot_required=reboot)
            except ValueError as e:
                return envelope(node, "set_config", result_type="ERROR", error=str(e)), 400
            except fc.NeedsAdminKey as e:
                return envelope(node, "set_config", result_type="NEEDS_ADMIN_KEY", error=str(e)), 403
            except TimeoutError as e:
                return envelope(node, "set_config", result_type="TIMEOUT", error=str(e)), 504

        @self.app.route("/api/nodes/<node>/status", methods=["GET"])
        def fleet_status(node):
            interface, err = iface_or_503()
            if err:
                return err
            st = fc.node_status(interface, node)
            reachable = node == "self" or st.get("last_heard") is not None
            return envelope(node, "status", reachable=reachable, status=st)

        @self.app.route("/api/nodes/<node>/ping", methods=["POST"])
        def fleet_ping(node):
            interface, err = iface_or_503()
            if err:
                return err
            ok = fc.ping(interface, node)
            return envelope(node, "ping", result_type="OK" if ok else "UNREACHABLE", reachable=ok)

    def start(self) -> None:
        """Start the web interface in a separate thread"""
        logging.info(f"Starting web interface on {self.host}:{self.port}")

        def run_server():
            # Disable Flask's default logging to avoid duplicate logs
            import logging as flask_logging

            flask_log = flask_logging.getLogger("werkzeug")
            flask_log.setLevel(logging.WARNING)

            self.app.run(host=self.host, port=self.port, debug=False, use_reloader=False)

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()
        logging.info(f"Web interface started at http://{self.host}:{self.port}")

    def is_running(self) -> bool:
        """Check if the web interface thread is alive"""
        return self.server_thread is not None and self.server_thread.is_alive()


