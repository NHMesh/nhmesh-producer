"""
This script is a producer for the NHMeshLive project.
It connects to a Meshtastic node and an MQTT broker,
and publishes received packets to the MQTT broker with automatic reconnection.
"""

import argparse
import atexit
import base64
import json
import logging
import os
import signal
import sys
import threading
import time
from os import environ
from typing import Any

import paho.mqtt.client as mqtt
from google.protobuf import json_format
from meshtastic.protobuf import mesh_pb2
from pubsub import pub
from nhmesh_producer.utils.connection_manager import ConnectionManager
from nhmesh_producer.utils.envdefault import EnvDefault
from nhmesh_producer.utils.node_cache import NodeCache
from nhmesh_producer.utils.traceroute_manager import TracerouteManager

logging.basicConfig(
    level=environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


class MeshtasticMQTTHandler:
    """
    A class to handle Meshtastic MQTT communication.
    This class connects to a Meshtastic node and an MQTT broker,
    and publishes received packets to the MQTT broker.

    Args:
        broker (str): The MQTT broker address.
        port (int): The MQTT broker port.
        topic (str): The root MQTT topic.
        tls (bool): Whether to use TLS/SSL.
        username (str): The MQTT username.
        password (str): The MQTT password.
        node_ip (str): The IP address of the Meshtastic node.
        traceroute_cooldown (int): Cooldown between traceroutes in seconds (default: 180).
        traceroute_interval (int): Interval between periodic traceroutes in seconds (default: 43200).
        traceroute_max_retries (int): Maximum retry attempts for failed traceroutes (default: 3).
        traceroute_max_backoff (int): Maximum backoff time in seconds (default: 86400).
    """

    def __init__(
        self,
        broker: str,
        port: int,
        topic: str,
        tls: bool,
        username: str | None,
        password: str | None,
        node_ip: str,
        traceroute_cooldown: int = 180,
        traceroute_interval: int = 43200,
        traceroute_max_retries: int = 3,
        traceroute_max_backoff: int = 86400,
        traceroute_persistence_file: str = "/tmp/traceroute_state.json",
    ) -> None:
        """
        Initializes the MeshtasticMQTTHandler with improved connection management.
        """
        self.broker = broker
        self.port = port
        self.topic = topic
        self.tls = tls
        self.username = username
        self.password = password
        self.node_ip = node_ip

        # Initialize connection manager
        self.connection_manager = ConnectionManager(node_ip)

        # Get interface and check if it's available
        interface = self.connection_manager.get_interface()
        if interface is None:
            raise Exception("Failed to get Meshtastic interface")

        # Get LoRa configuration with null checks
        try:
            self.lora_config = interface.localNode.localConfig.lora
            self.modem_preset = (
                "LongFast"
                if self.lora_config.modem_preset == 0
                else "MediumFast"
                if self.lora_config.modem_preset == 4
                else "Unknown"
            )
            self.channel_num = self.lora_config.channel_num
        except AttributeError as e:
            logging.warning(f"Failed to get LoRa configuration: {e}")
            # Set default values if LoRa config is not available
            self.lora_config = None
            self.modem_preset = "Unknown"
            self.channel_num = 0

        # MQTT client setup with callbacks
        self.mqtt_client = mqtt.Client()
        if self.username and self.password:
            self.mqtt_client.username_pw_set(
                username=self.username, password=self.password
            )
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self.mqtt_client.on_publish = self._on_mqtt_publish

        # MQTT connection state
        self.mqtt_connected = False
        self.mqtt_reconnect_attempts = 0
        self.max_mqtt_reconnect_attempts = 5
        self._shutdown_event = threading.Event()  # Thread-safe shutdown signal

        # Initialize Meshtastic connection
        if not self.connection_manager.connect():
            raise Exception("Failed to establish initial Meshtastic connection")

        # --- Node Cache and Traceroute Daemon Feature ---
        # Get interface for NodeCache and TracerouteManager initialization
        interface = self.connection_manager.get_interface()
        if interface is None:
            raise Exception(
                "Failed to get Meshtastic interface for NodeCache and TracerouteManager"
            )

        self.node_cache = NodeCache(interface)

        # Pass configuration parameters directly to TracerouteManager
        self.traceroute_manager = TracerouteManager(
            interface,
            self.node_cache,
            traceroute_cooldown,
            traceroute_interval,
            traceroute_max_retries,
            traceroute_max_backoff,
            traceroute_persistence_file,
        )

        # Subscribe to packet events AFTER traceroute_manager is initialized
        pub.subscribe(self.onReceive, "meshtastic.receive")  # type: ignore

        # Register cleanup handlers
        atexit.register(self.cleanup)

    def _on_mqtt_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        """Callback for MQTT connection"""
        if rc == 0:
            self.mqtt_connected = True
            self.mqtt_reconnect_attempts = 0
            logging.info("Connected to MQTT broker")
        else:
            logging.error(f"Failed to connect to MQTT broker: {rc}")

    def _on_mqtt_disconnect(self, client: Any, userdata: Any, rc: int) -> None:
        """Callback for MQTT disconnection"""
        self.mqtt_connected = False
        logging.warning(f"Disconnected from MQTT broker: {rc}")

    def _on_mqtt_publish(self, client: Any, userdata: Any, mid: int) -> None:
        """Callback for MQTT publish"""
        logging.debug(f"Message published: {mid}")

    def _update_interface_references(self) -> None:
        """Update interface references in NodeCache and TracerouteManager after reconnection"""
        interface = self.connection_manager.get_interface()
        if interface:
            self.node_cache.interface = interface
            self.traceroute_manager.interface = interface
            logging.info(
                "Updated interface references in NodeCache and TracerouteManager"
            )

    def _update_cache_from_packet(self, packet: dict[str, Any]) -> None:
        """
        Update cache from packet and delegate traceroute logic to TracerouteManager.

        Args:
            packet (dict): The received packet dictionary
        """
        # Update node cache and get whether this is a new node
        node_id = packet.get("fromId")
        if node_id is None:
            return

        is_new_node = self.node_cache.update_from_packet(
            packet, self.traceroute_manager
        )

        # Delegate traceroute queueing logic to TracerouteManager
        self.traceroute_manager.process_packet_for_traceroutes(node_id, is_new_node)

    def cleanup(self) -> None:
        """
        Properly cleanup all resources.
        """
        logging.info("[Cleanup] Starting cleanup process...")

        # Stop the main loop first
        self._shutdown_event.set()  # Signal shutdown to main thread

        # Cleanup TracerouteManager and save state first
        if hasattr(self, "traceroute_manager"):
            try:
                logging.info("[Cleanup] Cleaning up TracerouteManager...")
                self.traceroute_manager.cleanup()
                logging.info("[Cleanup] TracerouteManager cleaned up.")
            except Exception as e:
                logging.error(f"[Cleanup] Error cleaning up TracerouteManager: {e}")

        # Close connection manager (which handles interface cleanup)
        if hasattr(self, "connection_manager"):
            try:
                logging.info("[Cleanup] Closing ConnectionManager...")
                self.connection_manager.close()
                logging.info("[Cleanup] ConnectionManager closed.")
            except Exception as e:
                logging.error(f"[Cleanup] Error closing ConnectionManager: {e}")

        # Disconnect MQTT
        if hasattr(self, "mqtt_client"):
            try:
                logging.info("[Cleanup] Disconnecting MQTT client...")
                self.mqtt_client.disconnect()
                self.mqtt_client.loop_stop()
                logging.info("[Cleanup] MQTT client disconnected.")
            except Exception as e:
                logging.error(f"[Cleanup] Error disconnecting MQTT: {e}")

        logging.info("[Cleanup] Cleanup process completed.")

    def connect(self) -> None:
        """
        Connects to the MQTT broker and starts the MQTT loop.
        Connection to Meshtastic is managed by ConnectionManager with automatic reconnection.
        """
        try:
            # Ensure Meshtastic connection is established
            if not self.connection_manager.is_connected():
                if not self.connection_manager.reconnect():
                    raise Exception("Failed to establish Meshtastic connection")
                # Update interface references after reconnection
                self._update_interface_references()

            # Connect to MQTT broker
            self.mqtt_client.connect(self.broker, self.port, 60)
            self.mqtt_client.loop_start()  # Start background loop

            # Keep main thread alive but interruptible
            logging.info("Starting main loop, waiting for shutdown signal...")
            while not self._shutdown_event.is_set():
                self._shutdown_event.wait(timeout=1.0)  # Interruptible wait

            logging.info("Main loop exited, stopping MQTT loop...")
            self.mqtt_client.loop_stop()
            logging.info("Exiting connect() method...")

        except KeyboardInterrupt:
            logging.info("Received KeyboardInterrupt, cleaning up...")
            self.cleanup()
            print("Exiting...")
            sys.exit(0)
        except Exception as e:
            logging.error(f"Unexpected error: {e}")
            self.cleanup()
            raise

    def onReceive(self, packet: bytes | dict[str, Any] | str, interface: Any) -> None:
        """
        Handles incoming Meshtastic packets.
        Args:
            packet (bytes|dict|str): The received packet data (could be bytes, JSON string, or dict).
            interface: The Meshtastic interface that received the packet.
        """
        # Try to decode packet as JSON first
        packet_dict: dict[str, Any] | None = None
        if isinstance(packet, dict):
            packet_dict = packet
        elif isinstance(packet, bytes):
            try:
                packet_dict = json.loads(packet.decode("utf-8"))
            except Exception:
                # Not JSON, try protobuf
                try:
                    mesh_packet = mesh_pb2.MeshPacket()
                    mesh_packet.ParseFromString(packet)
                    # Convert protobuf to dict
                    packet_dict = json_format.MessageToDict(
                        mesh_packet, preserving_proto_field_name=True
                    )
                except Exception as e:
                    logging.error(f"Failed to decode packet as protobuf: {e}")
                    return
        else:  # isinstance(packet, str)
            try:
                packet_dict = json.loads(packet)
            except Exception:
                # Not JSON, try base64 decode then protobuf
                try:
                    packet_bytes = base64.b64decode(packet)
                    mesh_packet = mesh_pb2.MeshPacket()
                    mesh_packet.ParseFromString(packet_bytes)
                    packet_dict = json_format.MessageToDict(
                        mesh_packet, preserving_proto_field_name=True
                    )
                except Exception as e:
                    logging.error(f"Failed to decode packet string as protobuf: {e}")
                    return

        if packet_dict is None:
            logging.error("Failed to decode packet")
            return

        logging.info(
            f"[onReceive] Packet received from '{packet_dict.get('fromId', 'unknown')}' to '{packet_dict.get('to', 'unknown')}'"
        )
        logging.debug(f"[onReceive] Raw packet: {packet_dict}")

        self._update_cache_from_packet(packet_dict)

        out_packet: dict[str, Any] = {}
        for field_descriptor, field_value in packet_dict.items():
            out_packet[field_descriptor] = field_value

        # Get gateway ID from connection manager, with fallback
        if (
            hasattr(self.connection_manager, "connected_node_id")
            and self.connection_manager.connected_node_id
        ):
            out_packet["gatewayId"] = self.connection_manager.connected_node_id
        else:
            # Fallback - try to get it from interface if available
            interface = self.connection_manager.get_interface()
            if interface:
                try:
                    node_info = interface.getMyNodeInfo()
                    out_packet["gatewayId"] = node_info["user"]["id"]
                except Exception as e:
                    logging.warning(f"Failed to get gateway ID: {e}")
                    out_packet["gatewayId"] = "unknown"
            else:
                out_packet["gatewayId"] = "unknown"

        out_packet["source"] = "rf"
        out_packet["modem_preset"] = self.modem_preset
        out_packet["channel_num"] = self.channel_num

        self.publish_dict_to_mqtt(out_packet)

    def publish_dict_to_mqtt(self, payload: dict[str, Any]) -> None:
        """
        Publishes a dictionary payload to an MQTT topic.

        Args:
            payload (dict): The dictionary payload to publish.
        """

        topic_node = f"{self.topic}/{payload['fromId']}"
        payload_json = json.dumps(payload, default=str)

        logging.info(
            f"Publishing packet from '{payload['fromId']}' to MQTT topic '{topic_node}'"
        )

        # Publish the JSON payload to the specified topic
        self.mqtt_client.publish(topic_node, payload_json)


if __name__ == "__main__":
    """Main entry point for the Meshtastic MQTT handler."""

    # Global client reference for signal handlers
    client: MeshtasticMQTTHandler | None = None

    def signal_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signals gracefully."""
        signal_name = signal.Signals(signum).name
        logging.info(f"Received {signal_name}, cleaning up...")

        try:
            if client:
                client.cleanup()
            logging.info("Cleanup completed successfully")
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

        # The main thread should exit on its own now that shutdown event is set
        # If it doesn't exit within a reasonable time, force exit
        def force_exit() -> None:
            time.sleep(2.0)  # Give main thread 2 seconds to exit gracefully
            logging.warning("Main thread did not exit gracefully, forcing exit")
            os._exit(1)

        # Start force exit timer in background
        force_exit_thread = threading.Thread(target=force_exit, daemon=True)
        force_exit_thread.start()

    parser = argparse.ArgumentParser(description="Meshtastic MQTT Handler")
    parser.add_argument(
        "--broker",
        default="mqtt.nhmesh.live",
        action=EnvDefault,
        envvar="MQTT_ENDPOINT",
        help="MQTT broker address",
    )
    parser.add_argument(
        "--port",
        default=1883,
        type=int,
        action=EnvDefault,
        envvar="MQTT_PORT",
        help="MQTT broker port",
    )
    parser.add_argument(
        "--topic",
        default="msh/US/NH/",
        action=EnvDefault,
        envvar="MQTT_TOPIC",
        help="Root topic",
    )
    parser.add_argument("--tls", type=bool, default=False, help="Enable TLS/SSL")
    parser.add_argument(
        "--username", action=EnvDefault, envvar="MQTT_USERNAME", help="MQTT username"
    )
    parser.add_argument(
        "--password", action=EnvDefault, envvar="MQTT_PASSWORD", help="MQTT password"
    )
    parser.add_argument(
        "--node-ip", action=EnvDefault, envvar="NODE_IP", help="Node IP address"
    )
    parser.add_argument(
        "--traceroute-cooldown",
        default=180,
        type=int,
        action=EnvDefault,
        envvar="TRACEROUTE_COOLDOWN",
        help="Cooldown between traceroutes in seconds (default: 180)",
    )
    parser.add_argument(
        "--traceroute-interval",
        default=43200,
        type=int,
        action=EnvDefault,
        envvar="TRACEROUTE_INTERVAL",
        help="Interval between periodic traceroutes in seconds (default: 43200 = 12 hours)",
    )
    parser.add_argument(
        "--traceroute-max-retries",
        default=3,
        type=int,
        action=EnvDefault,
        envvar="TRACEROUTE_MAX_RETRIES",
        help="Maximum number of retry attempts for failed traceroutes (default: 3)",
    )
    parser.add_argument(
        "--traceroute-max-backoff",
        default=86400,
        type=int,
        action=EnvDefault,
        envvar="TRACEROUTE_MAX_BACKOFF",
        help="Maximum backoff time in seconds for failed nodes (default: 86400 = 24 hours)",
    )
    parser.add_argument(
        "--traceroute-persistence-file",
        default="/tmp/traceroute_state.json",
        action=EnvDefault,
        envvar="TRACEROUTE_PERSISTENCE_FILE",
        help="Path to file for persisting traceroute retry/backoff state (default: /tmp/traceroute_state.json)",
    )
    args = parser.parse_args()

    try:
        client = MeshtasticMQTTHandler(
            args.broker,
            args.port,
            args.topic,
            args.tls,
            args.username,
            args.password,
            args.node_ip,
            args.traceroute_cooldown,
            args.traceroute_interval,
            args.traceroute_max_retries,
            args.traceroute_max_backoff,
            args.traceroute_persistence_file,
        )

        # Register signal handlers for graceful shutdown AFTER client creation
        signal.signal(signal.SIGTERM, signal_handler)  # Docker stop
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C

        client.connect()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        if client:
            client.cleanup()
        sys.exit(1)
