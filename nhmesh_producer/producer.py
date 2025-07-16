"""
This script is a producer for the NHMeshLive project.
It connects to a Meshtastic node and an MQTT broker,
and publishes received packets to the MQTT broker with automatic reconnection.
"""

import logging
from os import environ
import sys
import signal
import paho.mqtt.client as mqtt
import json
import meshtastic
import meshtastic.tcp_interface
from pubsub import pub
import argparse
from utils.envdefault import EnvDefault
from utils.traceroute_manager import TracerouteManager
from utils.node_cache import NodeCache
import time


logging.basicConfig(
    level=environ.get('LOG_LEVEL', "INFO").upper(),
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
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
        traceroute_cooldown (int): Cooldown between traceroutes in seconds (default: 30).
        traceroute_interval (int): Interval between periodic traceroutes in seconds (default: 10800).
        traceroute_max_retries (int): Maximum retry attempts for failed traceroutes (default: 5).
        traceroute_max_backoff (int): Maximum backoff time in seconds (default: 86400).
    """
    
    def __init__(self, broker, port, topic, tls, username, password, node_ip, traceroute_cooldown=30, 
                 traceroute_interval=10800, traceroute_max_retries=5, traceroute_max_backoff=86400, traceroute_persistence_file='/tmp/traceroute_state.json'):
        """
        Initializes the MeshtasticMQTTHandler.
        """
        self.broker = broker
        self.port = port
        self.topic = topic
        self.tls = tls
        self.username = username
        self.password = password
        self.node_ip = node_ip
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds
        
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.username_pw_set(username=self.username, password=self.password)
        
        try:
            self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.node_ip)
            self.node_info = self.interface.getMyNodeInfo()
            self.connected_node_id = self.node_info["user"]["id"]
        except Exception as e:
            logging.error(f"Failed to setup Meshtastic interface: {e}")
            raise

        pub.subscribe(self.onReceive, "meshtastic.receive")

        # --- Node Cache and Traceroute Daemon Feature ---
        self.node_cache = NodeCache(self.interface)
        
        # Pass configuration parameters directly to TracerouteManager
        self.traceroute_manager = TracerouteManager(
            self.interface, 
            self.node_cache, 
            traceroute_cooldown,
            traceroute_interval,
            traceroute_max_retries,
            traceroute_max_backoff,
            traceroute_persistence_file,
        )

    def _update_cache_from_packet(self, packet):
        """
        Update cache from packet and delegate traceroute logic to TracerouteManager.
        
        Args:
            packet (dict): The received packet dictionary
        """
        # Update node cache and get whether this is a new node
        node_id = packet.get("fromId")
        if node_id is None:
            return
            
        is_new_node = self.node_cache.update_from_packet(packet, self.traceroute_manager)
        
        # Delegate traceroute queueing logic to TracerouteManager
        self.traceroute_manager.process_packet_for_traceroutes(node_id, is_new_node)

    def cleanup(self):
        """
        Properly cleanup all resources.
        """
        logging.info("[Cleanup] Starting cleanup process...")
        
        # Close interface
        if hasattr(self, 'interface'):
            try:
                self.interface.close()
                logging.info("[Cleanup] Meshtastic interface closed.")
            except Exception as e:
                logging.error(f"[Cleanup] Error closing interface: {e}")
        
        # Disconnect MQTT
        if hasattr(self, 'mqtt_client'):
            try:
                self.mqtt_client.disconnect()
                self.mqtt_client.loop_stop()
                logging.info("[Cleanup] MQTT client disconnected.")
            except Exception as e:
                logging.error(f"[Cleanup] Error disconnecting MQTT: {e}")
        
        # Cleanup TracerouteManager and save state
        if hasattr(self, 'traceroute_manager'):
            try:
                self.traceroute_manager.cleanup()
                logging.info("[Cleanup] TracerouteManager cleaned up.")
            except Exception as e:
                logging.error(f"[Cleanup] Error cleaning up TracerouteManager: {e}")

    def connect(self):
        """
        Connects to the MQTT broker and starts the MQTT loop.
        Includes reconnection logic for both MQTT and Meshtastic.
        """
        reconnect_attempts = 0
        
        while reconnect_attempts < self.max_reconnect_attempts:
            try:
                self.mqtt_client.connect(self.broker, self.port, 60)
                self.mqtt_client.loop_forever()
            except (BrokenPipeError, ConnectionError) as e:
                logging.error(f"Connection error: {e}")
                reconnect_attempts += 1
                
                if reconnect_attempts < self.max_reconnect_attempts:
                    logging.info(f"Attempting to reconnect in {self.reconnect_delay} seconds... (Attempt {reconnect_attempts}/{self.max_reconnect_attempts})")
                    time.sleep(self.reconnect_delay)
                    try:
                        self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.node_ip)
                        self.node_info = self.interface.getMyNodeInfo()
                        self.connected_node_id = self.node_info["user"]["id"]
                    except Exception as e:
                        logging.error(f"Failed to reconnect to Meshtastic: {e}")
                        continue
                else:
                    logging.error("Max reconnection attempts reached. Exiting...")
                    raise
            except KeyboardInterrupt:
                logging.info("Received KeyboardInterrupt, cleaning up...")
                self.cleanup()
                print("Exiting...")
                sys.exit(0)
            except Exception as e:
                logging.error(f"Unexpected error: {e}")
                self.cleanup()
                raise
        
    def onReceive(self, packet, interface): # called when a packet arrives
        """
        Handles incoming Meshtastic packets.
        Args:
            packet (bytes|dict|str): The received packet data (could be bytes, JSON string, or dict).
        """
        import json
        from meshtastic.protobuf import mesh_pb2
        import base64
        # Try to decode packet as JSON first
        packet_dict = None
        if isinstance(packet, dict):
            packet_dict = packet
        elif isinstance(packet, bytes):
            try:
                packet_dict = json.loads(packet.decode('utf-8'))
            except Exception:
                # Not JSON, try protobuf
                try:
                    mesh_packet = mesh_pb2.MeshPacket()
                    mesh_packet.ParseFromString(packet)
                    # Convert protobuf to dict
                    from google.protobuf import json_format
                    packet_dict = json_format.MessageToDict(mesh_packet, preserving_proto_field_name=True)
                except Exception as e:
                    logging.error(f"Failed to decode packet as protobuf: {e}")
                    return
        elif isinstance(packet, str):
            try:
                packet_dict = json.loads(packet)
            except Exception:
                # Not JSON, try base64 decode then protobuf
                try:
                    packet_bytes = base64.b64decode(packet)
                    mesh_packet = mesh_pb2.MeshPacket()
                    mesh_packet.ParseFromString(packet_bytes)
                    from google.protobuf import json_format
                    packet_dict = json_format.MessageToDict(mesh_packet, preserving_proto_field_name=True)
                except Exception as e:
                    logging.error(f"Failed to decode packet string as protobuf: {e}")
                    return
        else:
            logging.error(f"Unknown packet type: {type(packet)}")
            return

        logging.info(f"[onReceive] Packet received from '{packet_dict.get("fromId", "unknown")}' to '{packet_dict.get("to", "unknown")}'")
        logging.debug(f"[onReceive] Raw packet: {packet_dict}")

        self._update_cache_from_packet(packet_dict)

        out_packet = {}
        for field_descriptor, field_value in packet_dict.items():
            out_packet[field_descriptor] = field_value

        out_packet["gatewayId"] = self.connected_node_id
        out_packet["source"] = "rf"

        self.publish_dict_to_mqtt(out_packet)
    
    def publish_dict_to_mqtt(self, payload):
        """
        Publishes a dictionary payload to an MQTT topic.

        Args:
            payload (dict): The dictionary payload to publish.
        """
        
        topic_node = f"{self.topic}/{payload['fromId']}"
        payload = json.dumps(payload, default=str)
        
        # Publish the JSON payload to the specified topic
        self.mqtt_client.publish(topic_node, payload)


if __name__ == "__main__":
    """Main entry point for the Meshtastic MQTT handler."""
    
    # Global client reference for signal handlers
    client: MeshtasticMQTTHandler | None = None
    
    def signal_handler(signum, frame):
        """Handle shutdown signals gracefully."""
        signal_name = signal.Signals(signum).name
        logging.info(f"Received {signal_name}, cleaning up...")
        if client:
            client.cleanup()
        sys.exit(0)
    
    parser = argparse.ArgumentParser(description='Meshtastic MQTT Handler')
    parser.add_argument('--broker', default='mqtt.nhmesh.live', action=EnvDefault, envvar="MQTT_ENDPOINT", help='MQTT broker address')
    parser.add_argument('--port', default=1883, type=int, action=EnvDefault, envvar="MQTT_PORT", help='MQTT broker port')
    parser.add_argument('--topic', default='msh/US/NH/', action=EnvDefault, envvar="MQTT_TOPIC", help='Root topic')
    parser.add_argument('--tls', type=bool, default=False, help='Enable TLS/SSL')
    parser.add_argument('--username', action=EnvDefault, envvar="MQTT_USERNAME", help='MQTT username')
    parser.add_argument('--password', action=EnvDefault, envvar="MQTT_PASSWORD", help='MQTT password')
    parser.add_argument('--node-ip', action=EnvDefault, envvar="NODE_IP", help='Node IP address')
    parser.add_argument('--traceroute-cooldown', default=30, type=int, action=EnvDefault, envvar="TRACEROUTE_COOLDOWN", help='Cooldown between traceroutes in seconds (default: 30)')
    parser.add_argument('--traceroute-interval', default=10800, type=int, action=EnvDefault, envvar="TRACEROUTE_INTERVAL", help='Interval between periodic traceroutes in seconds (default: 10800 = 3 hours)')
    parser.add_argument('--traceroute-max-retries', default=5, type=int, action=EnvDefault, envvar="TRACEROUTE_MAX_RETRIES", help='Maximum number of retry attempts for failed traceroutes (default: 5)')
    parser.add_argument('--traceroute-max-backoff', default=86400, type=int, action=EnvDefault, envvar="TRACEROUTE_MAX_BACKOFF", help='Maximum backoff time in seconds for failed nodes (default: 86400 = 24 hours)')
    parser.add_argument('--traceroute-persistence-file', default='/tmp/traceroute_state.json', action=EnvDefault, envvar="TRACEROUTE_PERSISTENCE_FILE", help='Path to file for persisting traceroute retry/backoff state (default: /tmp/traceroute_state.json)')
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
            args.traceroute_persistence_file
        )
        
        # Register signal handlers for graceful shutdown AFTER client creation
        signal.signal(signal.SIGTERM, signal_handler)  # Docker stop
        signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
        
        client.connect()
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        if client:
            client.cleanup()
        sys.exit(1)