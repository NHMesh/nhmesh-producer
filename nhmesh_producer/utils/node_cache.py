import logging

from utils.number_utils import safe_float_list, safe_process_position


class NodeCache:
    """
    Keeps track of node information extracted from packets.
    """

    def __init__(self, interface):
        """
        Initialize the NodeCache.

        Args:
            interface: The Meshtastic interface for accessing node database
        """
        self.interface = interface
        self._node_cache = {}  # node_id -> {"position": (lat, lon, alt), "long_name": str}

    def get_node_info(self, node_id):
        """
        Get cached information for a node.

        Args:
            node_id (str): The node ID to look up

        Returns:
            dict: Node information with "position" and "long_name" keys, or empty dict if not found
        """
        return self._node_cache.get(str(node_id), {})

    def get_all_nodes(self):
        """
        Get all cached node IDs.

        Returns:
            list: List of all cached node IDs
        """
        return list(self._node_cache.keys())

    def has_node(self, node_id):
        """
        Check if a node exists in the cache.

        Args:
            node_id (str): The node ID to check

        Returns:
            bool: True if node exists in cache, False otherwise
        """
        return str(node_id) in self._node_cache

    def update_from_packet(self, packet, traceroute_manager=None):
        """
        Update node cache from incoming packet and process packet data.

        Args:
            packet (dict): The received packet dictionary
            traceroute_manager: Optional TracerouteManager instance to notify of traceroute responses

        Returns:
            bool: True if this is a new node, False if existing
        """
        # Pulling the node ID from the packet. Note that this is expected to be the
        # hexadecimal string representation of the node ID. This is usually prefixed
        # with an !
        node_id = packet.get("fromId")
        if node_id is None:
            return False

        node_id = str(node_id)  # Ensure node_id is always a string
        is_new_node = node_id not in self._node_cache
        entry = self._node_cache.setdefault(node_id, {"position": None, "long_name": None})
        decoded = packet.get("decoded", {})

        # Helper to get bytes from payload
        def get_payload_bytes(payload):
            if isinstance(payload, bytes):
                return payload
            elif isinstance(payload, str):
                import base64
                try:
                    return base64.b64decode(payload)
                except Exception:
                    return None
            else:
                return None

        # POSITION_APP
        if decoded.get("portnum") == "POSITION_APP":
            logging.info(f"[NodeCache] Processing POSITION_APP packet from node {node_id}")
            payload = decoded.get("payload")
            if not isinstance(payload, dict):
                payload_bytes = get_payload_bytes(payload)
                if payload_bytes:
                    try:
                        from meshtastic.protobuf import mesh_pb2
                        pos = mesh_pb2.Position()
                        pos.ParseFromString(payload_bytes)
                        if pos.latitude_i != 0 and pos.longitude_i != 0:
                            lat, lon, alt = safe_process_position(pos.latitude_i, pos.longitude_i, pos.altitude)
                            entry["position"] = (lat, lon, alt)
                            logging.info(f"[NodeCache] Updated position for node {node_id}: ({lat:.7f}, {lon:.7f})")
                        else:
                            entry["position"] = None
                            logging.debug(f"[NodeCache] Received empty position data for node {node_id}")
                    except Exception as e:
                        logging.warning(f"Error parsing position: {e}")

        # USER_APP
        if decoded.get("portnum") == "USER_APP":
            logging.info(f"[NodeCache] Processing USER_APP packet from node {node_id}")
            payload = decoded.get("payload")
            if not isinstance(payload, dict):
                payload_bytes = get_payload_bytes(payload)
                if payload_bytes:
                    try:
                        from meshtastic.protobuf import mesh_pb2
                        user = mesh_pb2.User()
                        user.ParseFromString(payload_bytes)
                        if user.long_name:
                            entry["long_name"] = user.long_name
                            logging.info(f"[NodeCache] Updated long_name for node {node_id}: '{user.long_name}'")
                        else:
                            logging.debug(f"[NodeCache] Received empty long_name for node {node_id}")
                    except Exception as e:
                        logging.warning(f"Error parsing user: {e}")

        # TRACEROUTE_APP
        if decoded.get("portnum") == "TRACEROUTE_APP":
            logging.info(f"[NodeCache] Processing TRACEROUTE_APP packet from node {node_id}")
            payload = decoded.get("payload")
            if not isinstance(payload, dict):
                payload_bytes = get_payload_bytes(payload)
                if payload_bytes:
                    try:
                        from meshtastic.protobuf import mesh_pb2
                        route = mesh_pb2.RouteDiscovery()
                        route.ParseFromString(payload_bytes)
                        # Add route information to the packet for MQTT publishing
                        packet["route"] = list(route.route)
                        packet["snr_towards"] = safe_float_list(list(route.snr_towards))
                        packet["route_back"] = list(route.route_back)
                        packet["snr_back"] = safe_float_list(list(route.snr_back))
                        logging.info(f"[NodeCache] Processed traceroute from node {node_id}: route={packet['route']}, route_back={packet['route_back']}")

                        # Notify traceroute manager that we received a response
                        if traceroute_manager:
                            traceroute_manager.record_traceroute_success(node_id)

                    except Exception as e:
                        logging.warning(f"Error parsing traceroute: {e}")

        # Try to update from interface nodes DB if available
        if hasattr(self.interface, "nodes") and node_id in self.interface.nodes:
            user = self.interface.nodes[node_id].get("user", {})
            if user:
                old_long_name = entry["long_name"]
                new_long_name = user.get("longName") or entry["long_name"]
                entry["long_name"] = new_long_name
                if old_long_name != new_long_name and new_long_name:
                    logging.info(f"[NodeCache] Updated long_name from interface DB for node {node_id}: '{new_long_name}'")

        # Log unhandled port numbers for debugging
        portnum = decoded.get("portnum")
        if portnum and portnum not in ["POSITION_APP", "USER_APP", "TRACEROUTE_APP"]:
            logging.info(f"[NodeCache] Received unhandled packet type '{portnum}' from node {node_id}")

        return is_new_node
