"""
This script is a producer for the NHMeshLive project.
It connects to a Meshtastic node and an MQTT broker,
and publishes received packets to the MQTT broker with automatic reconnection.
"""

import logging
from os import environ
import sys
import socket
import paho.mqtt.client as mqtt
import json
import meshtastic
import meshtastic.tcp_interface
from pubsub import pub
import argparse
from utils.envdefault import EnvDefault
from utils.number_utils import safe_float, safe_float_list, safe_process_position
import time
import threading
import queue
from datetime import datetime, timezone
from collections import defaultdict, deque
import signal
import atexit

logging.basicConfig(
    level=environ.get('LOG_LEVEL', "INFO").upper(),
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)

class ConnectionManager:
    """Manages connection health and automatic reconnection for Meshtastic interface"""
    
    def __init__(self, node_ip, reconnect_attempts=5, reconnect_delay=5, health_check_interval=30):
        self.node_ip = node_ip
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.health_check_interval = health_check_interval
        self.interface = None
        self.connected = False
        self.last_heartbeat = time.time()
        self.connection_errors = 0
        self.max_connection_errors = 10
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        
        # Start health monitoring thread
        self.health_thread = threading.Thread(target=self._health_monitor, daemon=True)
        self.health_thread.start()
        
    def connect(self):
        """Establish connection to Meshtastic node with error handling"""
        with self.lock:
            try:
                if self.interface:
                    try:
                        self.interface.close()
                    except Exception as e:
                        logging.warning(f"Error closing existing interface: {e}")
                
                logging.info(f"Connecting to Meshtastic node at {self.node_ip}")
                self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.node_ip)
                
                # Test connection by getting node info
                self.node_info = self.interface.getMyNodeInfo()
                self.connected_node_id = self.node_info["user"]["id"]
                
                self.connected = True
                self.connection_errors = 0
                self.last_heartbeat = time.time()
                
                logging.info(f"Successfully connected to node {self.connected_node_id}")
                return True
                
            except Exception as e:
                logging.error(f"Failed to connect to Meshtastic node: {e}")
                self.connected = False
                self.connection_errors += 1
                return False
    
    def reconnect(self):
        """Attempt to reconnect with exponential backoff"""
        attempts = 0
        while attempts < self.reconnect_attempts and not self.stop_event.is_set():
            attempts += 1
            logging.info(f"Reconnection attempt {attempts}/{self.reconnect_attempts}")
            
            if self.connect():
                return True
            
            # Exponential backoff
            delay = self.reconnect_delay * (2 ** (attempts - 1))
            logging.info(f"Reconnection failed, waiting {delay} seconds before next attempt")
            time.sleep(delay)
        
        logging.error("Max reconnection attempts reached")
        return False
    
    def _health_monitor(self):
        """Monitor connection health and trigger reconnection if needed"""
        while not self.stop_event.is_set():
            try:
                time.sleep(self.health_check_interval)
                
                if not self.connected or self.connection_errors >= self.max_connection_errors:
                    logging.warning("Connection health check failed, attempting reconnection")
                    self.reconnect()
                
                # Check if interface is still responsive
                if self.interface and self.connected:
                    try:
                        # Simple health check - try to get node info
                        self.interface.getMyNodeInfo()
                        self.last_heartbeat = time.time()
                    except Exception as e:
                        logging.warning(f"Health check failed: {e}")
                        self.connected = False
                        self.connection_errors += 1
                        
            except Exception as e:
                logging.error(f"Error in health monitor: {e}")
    
    def is_connected(self):
        """Check if currently connected"""
        return self.connected and self.interface is not None
    
    def get_interface(self):
        """Get the current interface, reconnecting if necessary"""
        if not self.is_connected():
            if not self.reconnect():
                return None
        return self.interface
    
    def close(self):
        """Close the connection and stop monitoring"""
        self.stop_event.set()
        if self.interface:
            try:
                self.interface.close()
            except Exception as e:
                logging.warning(f"Error closing interface: {e}")
        self.connected = False

class MeshtasticMQTTHandler:
    """
    A class to handle Meshtastic MQTT communication with improved resilience.
    This class connects to a Meshtastic node and an MQTT broker,
    and publishes received packets to the MQTT broker with automatic reconnection.
    """
    
    def __init__(self, broker, port, topic, tls, username, password, node_ip):
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
        
        # MQTT client setup with callbacks
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.username_pw_set(username=self.username, password=self.password)
        self.mqtt_client.on_connect = self._on_mqtt_connect
        self.mqtt_client.on_disconnect = self._on_mqtt_disconnect
        self.mqtt_client.on_publish = self._on_mqtt_publish
        
        # MQTT connection state
        self.mqtt_connected = False
        self.mqtt_reconnect_attempts = 0
        self.max_mqtt_reconnect_attempts = 5
        
        # Initialize Meshtastic connection
        if not self.connection_manager.connect():
            raise Exception("Failed to establish initial Meshtastic connection")
        
        # Subscribe to packet events
        pub.subscribe(self.onReceive, "meshtastic.receive")

        # --- Traceroute Daemon Feature ---
        self._node_cache = {}  # node_id -> {"position": (lat, lon, alt), "long_name": str}
        self._last_traceroute_time = {}
        self._TRACEROUTE_INTERVAL = 3 * 60 * 60  # 3 hours
        self._traceroute_queue = queue.Queue()
        self._traceroute_worker_thread = threading.Thread(target=self._traceroute_worker, daemon=True)
        self._traceroute_worker_thread.start()
        logging.info("Traceroute worker thread started.")
        
        # --- Traceroute Reply Tracking ---
        self._pending_traceroutes = {}  # node_id -> {"timestamp": time, "retries": int, "max_wait": time}
        self._traceroute_replies = {}  # node_id -> reply_data
        self._traceroute_lock = threading.Lock()
        
        # --- Traceroute Metrics Tracking ---
        self._total_traceroutes_sent = 0
        self._total_traceroutes_received = 0
        self._traceroute_response_times = []  # List of response times for calculating averages
        self._last_cleanup_time = None
        
        # Start traceroute cleanup thread
        self._traceroute_cleanup_thread = threading.Thread(target=self._traceroute_cleanup_worker, daemon=True)
        self._traceroute_cleanup_thread.start()
        logging.info("Traceroute cleanup thread started.")

        # --- Web Interface Feature ---
        # Will be set after args are parsed
        self.web_enabled = False
        self.web_host = '0.0.0.0'
        self.web_port = 5001
        
        # Register cleanup handlers
        atexit.register(self.cleanup)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logging.info(f"Received signal {signum}, shutting down gracefully...")
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        """Clean up resources on shutdown"""
        logging.info("Cleaning up resources...")
        try:
            self.connection_manager.close()
            if self.mqtt_client:
                self.mqtt_client.disconnect()
                self.mqtt_client.loop_stop()
        except Exception as e:
            logging.error(f"Error during cleanup: {e}")

    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """MQTT connection callback"""
        if rc == 0:
            logging.info("Successfully connected to MQTT broker")
            self.mqtt_connected = True
            self.mqtt_reconnect_attempts = 0
        else:
            logging.error(f"Failed to connect to MQTT broker with code: {rc}")
            self.mqtt_connected = False

    def _on_mqtt_disconnect(self, client, userdata, rc):
        """MQTT disconnection callback"""
        logging.warning(f"Disconnected from MQTT broker with code: {rc}")
        self.mqtt_connected = False
        
        if rc != 0:
            # Unexpected disconnection, attempt to reconnect
            self.mqtt_reconnect_attempts += 1
            if self.mqtt_reconnect_attempts <= self.max_mqtt_reconnect_attempts:
                logging.info(f"Attempting MQTT reconnection ({self.mqtt_reconnect_attempts}/{self.max_mqtt_reconnect_attempts})")
                time.sleep(5)  # Wait before reconnecting
                try:
                    self.mqtt_client.reconnect()
                except Exception as e:
                    logging.error(f"MQTT reconnection failed: {e}")

    def _on_mqtt_publish(self, client, userdata, mid):
        """MQTT publish callback"""
        logging.debug(f"Successfully published message with ID: {mid}")

    def configure_web_interface(self, enabled, host, port):
        """Configure and initialize web interface"""
        self.web_enabled = enabled
        self.web_host = host
        self.web_port = port
        
        if self.web_enabled:
            self._init_web_interface()
            logging.info(f"Web interface enabled on {self.web_host}:{self.web_port}")
        else:
            logging.info("Web interface disabled")

    def _init_web_interface(self):
        """Initialize web interface data structures and Flask app"""
        # Web interface data storage
        self.web_nodes = defaultdict(dict)  # node_id -> node_data
        self.web_recent_packets = deque(maxlen=1000)  # Last 1000 packets
        self.web_traceroutes = defaultdict(list)  # node_id -> list of traceroute data
        self.web_network_stats = {
            'total_packets': 0,
            'active_nodes': 0,
            'total_traceroutes': 0,
            'last_update': None
        }
        
        # Start web interface in background thread
        self._web_interface_thread = threading.Thread(target=self._start_web_interface, daemon=True)
        self._web_interface_thread.start()
        
        # Start web stats update thread
        self._web_stats_thread = threading.Thread(target=self._update_web_stats, daemon=True)
        self._web_stats_thread.start()

    def _start_web_interface(self):
        """Start the Flask web interface in a background thread"""
        try:
            from flask import Flask, render_template, jsonify
            import webbrowser
            
            app = Flask(__name__)
            
            def json_serializable(obj):
                """Convert objects to JSON serializable format"""
                if isinstance(obj, bytes):
                    return obj.hex()  # Convert bytes to hex string
                elif hasattr(obj, 'isoformat'):  # Handle datetime objects
                    return obj.isoformat()
                elif hasattr(obj, '__dict__'):  # Handle custom objects
                    return str(obj)
                else:
                    return str(obj)
            
            def safe_jsonify(data):
                """Safely convert data to JSON, handling non-serializable objects"""
                import json
                return json.dumps(data, default=json_serializable, ensure_ascii=False)
            
            @app.route('/')
            def index():
                return render_template('dashboard.html')
            
            @app.route('/traceroute')
            def traceroute():
                return render_template('traceroute.html')
            
            @app.route('/api/nodes')
            def get_nodes():
                nodes_data = {}
                for node_id, node_data in self.web_nodes.items():
                    nodes_data[node_id] = node_data
                return safe_jsonify(nodes_data), 200, {'Content-Type': 'application/json'}
            
            @app.route('/api/recent_packets')
            def get_recent_packets():
                return safe_jsonify(list(self.web_recent_packets)), 200, {'Content-Type': 'application/json'}
            
            @app.route('/api/stats')
            def get_stats():
                return safe_jsonify(self.web_network_stats), 200, {'Content-Type': 'application/json'}
            
            @app.route('/api/node/<node_id>')
            def get_node(node_id):
                node_data = self.web_nodes.get(node_id)
                if node_data is None:
                    return safe_jsonify({'error': 'Node not found'}), 404, {'Content-Type': 'application/json'}
                return safe_jsonify(node_data), 200, {'Content-Type': 'application/json'}
            
            @app.route('/api/traceroutes')
            def get_traceroutes():
                """Get all traceroute data"""
                return safe_jsonify(dict(self.web_traceroutes)), 200, {'Content-Type': 'application/json'}
            
            @app.route('/api/traceroutes/<node_id>')
            def get_node_traceroutes(node_id):
                """Get traceroute data for a specific node"""
                traceroutes = self.web_traceroutes.get(node_id, [])
                return safe_jsonify(traceroutes), 200, {'Content-Type': 'application/json'}
            
            @app.route('/api/network-topology')
            def get_network_topology():
                """Get network topology analysis based on traceroute data"""
                topology = self._analyze_network_topology()
                return safe_jsonify(topology), 200, {'Content-Type': 'application/json'}
            
            @app.route('/api/traceroute-queue')
            def get_traceroute_queue():
                """Get current traceroute queue status"""
                # Ensure traceroute data structures exist
                if not hasattr(self, '_pending_traceroutes'):
                    self._pending_traceroutes = {}
                if not hasattr(self, '_traceroute_replies'):
                    self._traceroute_replies = {}
                if not hasattr(self, '_traceroute_queue'):
                    self._traceroute_queue = queue.Queue()
                
                with self._traceroute_lock:
                    queue_status = {
                        'pending_traceroutes': dict(self._pending_traceroutes),
                        'traceroute_replies': dict(self._traceroute_replies),
                        'queue_size': self._traceroute_queue.qsize(),
                        'total_pending': len(self._pending_traceroutes),
                        'total_replies': len(self._traceroute_replies),
                        'last_cleanup': getattr(self, '_last_cleanup_time', None)
                    }
                return safe_jsonify(queue_status), 200, {'Content-Type': 'application/json'}
            
            @app.route('/api/traceroute-metrics')
            def get_traceroute_metrics():
                """Get comprehensive traceroute metrics"""
                current_time = time.time()
                
                # Ensure traceroute data structures exist
                if not hasattr(self, '_pending_traceroutes'):
                    self._pending_traceroutes = {}
                if not hasattr(self, '_traceroute_replies'):
                    self._traceroute_replies = {}
                if not hasattr(self, '_total_traceroutes_sent'):
                    self._total_traceroutes_sent = 0
                if not hasattr(self, '_total_traceroutes_received'):
                    self._total_traceroutes_received = 0
                if not hasattr(self, '_traceroute_response_times'):
                    self._traceroute_response_times = []
                
                # Calculate metrics from pending traceroutes
                pending_metrics = {
                    'total_pending': len(self._pending_traceroutes),
                    'pending_by_age': {'0-30s': 0, '30s-1m': 0, '1m-5m': 0, '5m+': 0},
                    'oldest_pending': None,
                    'newest_pending': None
                }
                
                with self._traceroute_lock:
                    for node_id, pending_data in self._pending_traceroutes.items():
                        age = current_time - pending_data['timestamp']
                        if age <= 30:
                            pending_metrics['pending_by_age']['0-30s'] += 1
                        elif age <= 60:
                            pending_metrics['pending_by_age']['30s-1m'] += 1
                        elif age <= 300:
                            pending_metrics['pending_by_age']['1m-5m'] += 1
                        else:
                            pending_metrics['pending_by_age']['5m+'] += 1
                        
                        if not pending_metrics['oldest_pending'] or age > (current_time - pending_metrics['oldest_pending']['timestamp']):
                            pending_metrics['oldest_pending'] = {
                                'node_id': node_id,
                                'timestamp': pending_data['timestamp'],
                                'age_seconds': age
                            }
                        
                        if not pending_metrics['newest_pending'] or age < (current_time - pending_metrics['newest_pending']['timestamp']):
                            pending_metrics['newest_pending'] = {
                                'node_id': node_id,
                                'timestamp': pending_data['timestamp'],
                                'age_seconds': age
                            }
                
                # Calculate success rate from recent traceroutes
                recent_traceroutes = []
                for node_id, routes in self.web_traceroutes.items():
                    if routes:
                        latest = routes[-1]
                        recent_traceroutes.append({
                            'node_id': node_id,
                            'timestamp': latest['timestamp'],
                            'hop_count': latest['hop_count'],
                            'route_quality': latest['route_quality'],
                            'avg_snr': latest['avg_snr_towards']
                        })
                
                # Sort by timestamp (newest first)
                recent_traceroutes.sort(key=lambda x: x['timestamp'], reverse=True)
                
                metrics = {
                    'queue_status': pending_metrics,
                    'recent_traceroutes': recent_traceroutes[:10],  # Last 10
                    'success_rate': self._calculate_traceroute_success_rate(),
                    'average_response_time': self._calculate_average_response_time(),
                    'total_traceroutes_sent': getattr(self, '_total_traceroutes_sent', 0),
                    'total_traceroutes_received': getattr(self, '_total_traceroutes_received', 0),
                    'last_traceroute_time': self._last_traceroute_time,
                    'queue_size': self._traceroute_queue.qsize()
                }
                
                return safe_jsonify(metrics), 200, {'Content-Type': 'application/json'}
            

            
            # Start Flask app
            logging.info(f"Starting web interface on {self.web_host}:{self.web_port}")
            app.run(host=self.web_host, port=self.web_port, debug=False, use_reloader=False)
            
        except ImportError as e:
            logging.error(f"Flask not available, web interface disabled: {e}")
        except Exception as e:
            logging.error(f"Failed to start web interface: {e}")

    def _update_web_interface(self, packet_dict):
        """Update web interface data with new packet"""
        if not self.web_enabled:
            return
            
        try:
            # Extract node ID from packet
            node_id = packet_dict.get('fromId') or packet_dict.get('from_id_str')
            if not node_id:
                return
            
            # Update node data
            self._update_web_node_data(node_id, packet_dict)
            
            # Process traceroute data if available
            self._process_traceroute_data(packet_dict)
            
            # Add to recent packets
            packet_dict['received_at'] = datetime.now(timezone.utc).isoformat()
            self.web_recent_packets.append(packet_dict)
            
            # Update stats
            self.web_network_stats['total_packets'] += 1
            self.web_network_stats['last_update'] = datetime.now(timezone.utc).isoformat()
            
        except Exception as e:
            logging.error(f"Error updating web interface: {e}")

    def _update_web_node_data(self, node_id, packet):
        """Update web interface node information with latest packet data"""
        node_data = self.web_nodes[node_id]
        
        # Update basic info
        node_data['node_id'] = node_id
        node_data['last_seen'] = datetime.now(timezone.utc).isoformat()
        node_data['packet_count'] = node_data.get('packet_count', 0) + 1
        
        # Update position if available
        if 'latitude' in packet and 'longitude' in packet:
            node_data['position'] = {
                'latitude': packet['latitude'],
                'longitude': packet['longitude'],
                'altitude': packet.get('altitude'),
                'timestamp': packet.get('timestamp')
            }
        
        # Update telemetry data
        if 'battery_level' in packet:
            node_data['battery_level'] = packet['battery_level']
        if 'voltage' in packet:
            node_data['voltage'] = packet['voltage']
        if 'uptime_seconds' in packet:
            node_data['uptime_seconds'] = packet['uptime_seconds']
        
        # Update signal quality
        if 'rssi' in packet:
            node_data['rssi'] = packet['rssi']
        if 'snr' in packet:
            node_data['snr'] = packet['snr']
        
        # Update node info
        if 'longname' in packet:
            node_data['longname'] = packet['longname']
        if 'shortname' in packet:
            node_data['shortname'] = packet['shortname']
        if 'role' in packet:
            node_data['role'] = packet['role']
        if 'hardware' in packet:
            node_data['hardware'] = packet['hardware']
        
        # Update hops info
        if 'hops_away' in packet:
            node_data['hops_away'] = packet['hops_away']
        
        # Update channel info
        if 'channel' in packet:
            node_data['channel'] = packet['channel']

    def _process_traceroute_data(self, packet):
        """Process traceroute data from packets"""
        try:
            # Check if this is a traceroute packet
            if 'route' in packet and 'snr_towards' in packet:
                source_node = packet.get('fromId') or packet.get('from_id_str')
                if not source_node:
                    return
                
                # Create traceroute entry
                traceroute_data = {
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'source_node': source_node,
                    'route': packet.get('route', []),
                    'snr_towards': packet.get('snr_towards', []),
                    'route_back': packet.get('route_back', []),
                    'snr_back': packet.get('snr_back', []),
                    'hop_count': len(packet.get('route', [])),
                    'avg_snr_towards': self._calculate_average_snr(packet.get('snr_towards', [])),
                    'avg_snr_back': self._calculate_average_snr(packet.get('snr_back', [])),
                    'route_quality': self._calculate_route_quality(packet.get('snr_towards', []))
                }
                
                # Store traceroute data (keep last 10 for each node)
                self.web_traceroutes[source_node].append(traceroute_data)
                if len(self.web_traceroutes[source_node]) > 10:
                    self.web_traceroutes[source_node].pop(0)
                
                # Update stats
                self.web_network_stats['total_traceroutes'] += 1
                
                logging.info(f"[Web] Processed traceroute for node {source_node}: {traceroute_data['hop_count']} hops, quality: {traceroute_data['route_quality']}")
                
        except Exception as e:
            logging.error(f"Error processing traceroute data: {e}")

    def _calculate_average_snr(self, snr_list):
        """Calculate average SNR from a list of SNR values"""
        if not snr_list:
            return None
        valid_snr = [s for s in snr_list if s is not None and s != 0]
        return sum(valid_snr) / len(valid_snr) if valid_snr else None

    def _calculate_route_quality(self, snr_list):
        """Calculate route quality score based on SNR values"""
        if not snr_list:
            return 'unknown'
        
        valid_snr = [s for s in snr_list if s is not None and s != 0]
        if not valid_snr:
            return 'unknown'
        
        avg_snr = sum(valid_snr) / len(valid_snr)
        
        if avg_snr >= 10:
            return 'excellent'
        elif avg_snr >= 5:
            return 'good'
        elif avg_snr >= 0:
            return 'fair'
        else:
            return 'poor'

    def _analyze_network_topology(self):
        """Analyze network topology based on traceroute data"""
        try:
            topology = {
                'total_nodes': len(self.web_nodes),
                'nodes_with_traceroutes': len(self.web_traceroutes),
                'total_routes': sum(len(routes) for routes in self.web_traceroutes.values()),
                'route_statistics': {
                    'avg_hops': 0,
                    'max_hops': 0,
                    'min_hops': 0,
                    'route_quality_distribution': {
                        'excellent': 0,
                        'good': 0,
                        'fair': 0,
                        'poor': 0,
                        'unknown': 0
                    }
                },
                'node_connectivity': {},
                'recent_traceroutes': []
            }
            
            # Calculate route statistics
            all_hops = []
            all_qualities = []
            
            for node_id, routes in self.web_traceroutes.items():
                if routes:
                    latest_route = routes[-1]  # Most recent route
                    all_hops.append(latest_route['hop_count'])
                    all_qualities.append(latest_route['route_quality'])
                    
                    # Add to recent traceroutes
                    topology['recent_traceroutes'].append({
                        'node_id': node_id,
                        'node_name': self.web_nodes.get(node_id, {}).get('longname', node_id),
                        'timestamp': latest_route['timestamp'],
                        'hop_count': latest_route['hop_count'],
                        'route_quality': latest_route['route_quality'],
                        'avg_snr': latest_route['avg_snr_towards']
                    })
                    
                    # Calculate node connectivity
                    topology['node_connectivity'][node_id] = {
                        'total_routes': len(routes),
                        'latest_route': latest_route,
                        'route_history': [r['route_quality'] for r in routes[-5:]]  # Last 5 routes
                    }
            
            # Calculate statistics
            if all_hops:
                topology['route_statistics']['avg_hops'] = sum(all_hops) / len(all_hops)
                topology['route_statistics']['max_hops'] = max(all_hops)
                topology['route_statistics']['min_hops'] = min(all_hops)
            
            if all_qualities:
                for quality in all_qualities:
                    topology['route_statistics']['route_quality_distribution'][quality] += 1
            
            # Sort recent traceroutes by timestamp (newest first)
            topology['recent_traceroutes'].sort(key=lambda x: x['timestamp'], reverse=True)
            
            return topology
            
        except Exception as e:
            logging.error(f"Error analyzing network topology: {e}")
            return {'error': str(e)}

    def _update_web_stats(self):
        """Update web interface statistics periodically"""
        while True:
            try:
                if self.web_enabled:
                    # Count active nodes (seen in last 10 minutes)
                    cutoff_time = datetime.now(timezone.utc).timestamp() - 600
                    active_nodes = 0
                    
                    for node_data in self.web_nodes.values():
                        if 'last_seen' in node_data:
                            last_seen = datetime.fromisoformat(node_data['last_seen'].replace('Z', '+00:00'))
                            if last_seen.timestamp() > cutoff_time:
                                active_nodes += 1
                    
                    self.web_network_stats['active_nodes'] = active_nodes
                
                time.sleep(30)  # Update every 30 seconds
                
            except Exception as e:
                logging.error(f"Web stats update error: {e}")
                time.sleep(30)

    def _format_position(self, pos):
        if pos is None:
            return "UNKNOWN"
        lat, lon, alt = pos
        s = f"({lat:.7f}, {lon:.7f})"
        if alt is not None:
            s += f" {alt}m"
        return s

    def _update_cache_from_packet(self, packet):
        node_id = packet.get("from")
        if node_id is None:
            return
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
                        else:
                            entry["position"] = None
                    except Exception as e:
                        logging.warning(f"Error parsing position: {e}")
        # USER_APP
        if decoded.get("portnum") == "USER_APP":
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
                    except Exception as e:
                        logging.warning(f"Error parsing user: {e}")
        # TRACEROUTE_APP
        if decoded.get("portnum") == "TRACEROUTE_APP":
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
                        packet["snr_towards"] = safe_float_list(route.snr_back)
                        packet["route_back"] = list(route.route_back)
                        packet["snr_back"] = safe_float_list(route.snr_towards)
                        
                        # Store traceroute reply for waiting requests
                        with self._traceroute_lock:
                            if node_id in self._pending_traceroutes:
                                self._traceroute_replies[node_id] = {
                                    "route": list(route.route),
                                    "snr_towards": safe_float_list(route.snr_back),
                                    "route_back": list(route.route_back),
                                    "snr_back": safe_float_list(route.snr_towards),
                                    "timestamp": time.time()
                                }
                                logging.info(f"[Traceroute] Stored reply for pending traceroute to node {node_id}")
                                logging.info(f"[Traceroute] Route data: {list(route.route)} | SNR: {safe_float_list(route.snr_back)}")
                            else:
                                logging.info(f"[Traceroute] Received traceroute reply from node {node_id} but no pending request found")
                        
                    except Exception as e:
                        logging.warning(f"Error parsing traceroute: {e}")
        # Try to update from interface nodes DB if available
        if hasattr(self.connection_manager.get_interface(), "nodes") and node_id in self.connection_manager.get_interface().nodes:
            user = self.connection_manager.get_interface().nodes[node_id].get("user", {})
            if user:
                entry["long_name"] = user.get("longName") or entry["long_name"]
        # Enqueue traceroute for new nodes
        if is_new_node:
            logging.info(f"[Traceroute] New node discovered: {node_id}, enqueuing traceroute job.")
            self._traceroute_queue.put((node_id, 0))  # 0 retries so far
        # Periodic re-traceroute
        now = time.time()
        last_time = self._last_traceroute_time.get(node_id, 0)
        if now - last_time > self._TRACEROUTE_INTERVAL:
            logging.info(f"[Traceroute] Periodic traceroute needed for node {node_id}, enqueuing job.")
            self._traceroute_queue.put((node_id, 0))

    def _run_traceroute(self, node_id):
        node_id = str(node_id)  # Ensure node_id is always a string
        entry = self._node_cache.get(node_id, {})
        long_name = entry.get("long_name")
        pos = entry.get("position")
        logging.info(f"[Traceroute] Running traceroute for Node {node_id} | Long name: {long_name if long_name else 'UNKNOWN'} | Position: {self._format_position(pos)}")
        
        try:
            # Log node info before traceroute
            try:
                info = self.connection_manager.get_interface().getMyNodeInfo()
                logging.info(f"[Traceroute] Node info before traceroute: {info}")
            except Exception as e:
                logging.error(f"[Traceroute] Failed to get node info before traceroute: {e}")
            
            # Pre traceroute log
            logging.info(f"[Traceroute] About to send traceroute to {node_id}")
            
            # Mark this traceroute as pending
            with self._traceroute_lock:
                self._pending_traceroutes[node_id] = {
                    "timestamp": time.time(),
                    "retries": 0,
                    "max_wait": 30  # Wait up to 30 seconds for reply
                }
                self._total_traceroutes_sent += 1
            
            # Send the traceroute command
            result = [None]
            def target():
                try:
                    self.connection_manager.get_interface().sendTraceRoute(dest=node_id, hopLimit=10)
                    result[0] = True
                except Exception as e:
                    import traceback
                    print(traceback.format_exc())
                    result[0] = e
            
            t = threading.Thread(target=target)
            t.start()
            t.join(timeout=5)  # 5 second timeout for sending the command
            
            if t.is_alive():
                logging.error(f"[Traceroute] sendTraceRoute command to node {node_id} timed out!")
                with self._traceroute_lock:
                    if node_id in self._pending_traceroutes:
                        del self._pending_traceroutes[node_id]
                return False
            
            if result[0] is not True:
                logging.error(f"[Traceroute] Error sending traceroute to node {node_id}: {result[0]}")
                with self._traceroute_lock:
                    if node_id in self._pending_traceroutes:
                        del self._pending_traceroutes[node_id]
                return False
            
            logging.info(f"[Traceroute] Traceroute command sent for node {node_id}, waiting for reply...")
            
            # Wait for the traceroute reply
            start_time = time.time()
            while time.time() - start_time < 30:  # Wait up to 30 seconds for reply
                with self._traceroute_lock:
                    if node_id in self._traceroute_replies:
                        # Reply received!
                        reply_data = self._traceroute_replies[node_id]
                        del self._traceroute_replies[node_id]
                        del self._pending_traceroutes[node_id]
                        
                        response_time = time.time() - start_time
                        self._traceroute_response_times.append(response_time)
                        self._total_traceroutes_received += 1
                        
                        # Keep only last 100 response times
                        if len(self._traceroute_response_times) > 100:
                            self._traceroute_response_times.pop(0)
                        
                        self._last_traceroute_time[node_id] = time.time()
                        logging.info(f"[Traceroute] Traceroute reply received for node {node_id} after {response_time:.1f}s")
                        logging.info(f"[Traceroute] Route: {reply_data.get('route', [])} | SNR: {reply_data.get('snr_towards', [])}")
                        return True
                
                time.sleep(0.5)  # Check every 500ms
            
            # Timeout waiting for reply
            logging.warning(f"[Traceroute] No reply received from node {node_id} within 30 seconds")
            with self._traceroute_lock:
                if node_id in self._pending_traceroutes:
                    del self._pending_traceroutes[node_id]
            return False
            
        except Exception as e:
            logging.error(f"[Traceroute] Unexpected error sending traceroute to node {node_id}: {e}")
            with self._traceroute_lock:
                if node_id in self._pending_traceroutes:
                    del self._pending_traceroutes[node_id]
            return False

    def _traceroute_worker(self):
        while True:
            try:
                node_id, retries = self._traceroute_queue.get()
                logging.info(f"[Traceroute] Worker picked up job for node {node_id}, attempt {retries+1}.")
                success = self._run_traceroute(node_id)
                if not success:
                    if retries < 2:  # Retry up to 2 times
                        logging.warning(f"[Traceroute] Failed to traceroute node {node_id}, retrying in 10 seconds... (attempt {retries+1}/3)")
                        time.sleep(10)
                        self._traceroute_queue.put((node_id, retries + 1))
                    else:
                        logging.error(f"[Traceroute] Failed to traceroute node {node_id} after 3 attempts.")
                else:
                    logging.info(f"[Traceroute] Traceroute for node {node_id} completed successfully.")
                
                # Clean up stale pending traceroutes
                self._cleanup_stale_traceroutes()
                
            except Exception as e:
                logging.error(f"[Traceroute] Worker encountered error: {e}")

    def _cleanup_stale_traceroutes(self):
        """Clean up traceroute requests that have been pending too long"""
        current_time = time.time()
        with self._traceroute_lock:
            stale_nodes = []
            for node_id, pending_data in self._pending_traceroutes.items():
                if current_time - pending_data["timestamp"] > pending_data["max_wait"]:
                    stale_nodes.append(node_id)
            
            for node_id in stale_nodes:
                logging.warning(f"[Traceroute] Cleaning up stale traceroute request for node {node_id}")
                del self._pending_traceroutes[node_id]
                if node_id in self._traceroute_replies:
                    del self._traceroute_replies[node_id]

    def get_traceroute_status(self):
        """Get current status of pending traceroutes for debugging"""
        with self._traceroute_lock:
            return {
                "pending_traceroutes": dict(self._pending_traceroutes),
                "traceroute_replies": dict(self._traceroute_replies),
                "total_pending": len(self._pending_traceroutes),
                "total_replies": len(self._traceroute_replies)
            }

    def _traceroute_cleanup_worker(self):
        """Periodically clean up stale traceroute requests"""
        while True:
            try:
                time.sleep(60)  # Check every minute
                self._cleanup_stale_traceroutes()
                self._last_cleanup_time = time.time()
            except Exception as e:
                logging.error(f"Traceroute cleanup worker error: {e}")

    def _calculate_traceroute_success_rate(self):
        """Calculate traceroute success rate based on recent activity"""
        if self._total_traceroutes_sent == 0:
            return 0.0
        
        # Calculate success rate from last 24 hours
        cutoff_time = time.time() - (24 * 60 * 60)  # 24 hours ago
        recent_successes = 0
        recent_attempts = 0
        
        # Count recent successful traceroutes
        for node_id, routes in self.web_traceroutes.items():
            if routes:
                latest_route = routes[-1]
                route_time = datetime.fromisoformat(latest_route['timestamp'].replace('Z', '+00:00')).timestamp()
                if route_time > cutoff_time:
                    recent_successes += 1
        
        # Estimate recent attempts (this is approximate)
        recent_attempts = recent_successes + len([p for p in self._pending_traceroutes.values() 
                                                if p['timestamp'] > cutoff_time])
        
        if recent_attempts == 0:
            return 0.0
        
        return (recent_successes / recent_attempts) * 100

    def _calculate_average_response_time(self):
        """Calculate average traceroute response time"""
        if not self._traceroute_response_times:
            return None
        
        # Keep only recent response times (last 100)
        recent_times = self._traceroute_response_times[-100:]
        return sum(recent_times) / len(recent_times)

    def connect(self):
        """
        Connects to the MQTT broker and starts the MQTT loop.
        Includes improved reconnection logic for both MQTT and Meshtastic.
        """
        try:
            # Connect to MQTT broker
            logging.info(f"Connecting to MQTT broker at {self.broker}:{self.port}")
            self.mqtt_client.connect(self.broker, self.port, 60)
            
            # Start MQTT loop in a separate thread to allow for graceful handling
            self.mqtt_client.loop_start()
            
            # Main loop with connection monitoring
            while True:
                try:
                    # Check connection health
                    if not self.connection_manager.is_connected():
                        logging.warning("Meshtastic connection lost, attempting reconnection...")
                        if not self.connection_manager.reconnect():
                            logging.error("Failed to reconnect to Meshtastic, exiting...")
                            break
                    
                    if not self.mqtt_connected:
                        logging.warning("MQTT connection lost, attempting reconnection...")
                        try:
                            self.mqtt_client.reconnect()
                        except Exception as e:
                            logging.error(f"MQTT reconnection failed: {e}")
                    
                    # Sleep to prevent busy waiting
                    time.sleep(10)
                    
                except KeyboardInterrupt:
                    logging.info("Received interrupt signal, shutting down...")
                    break
                except Exception as e:
                    logging.error(f"Error in main loop: {e}")
                    time.sleep(5)  # Wait before retrying
                    
        except Exception as e:
            logging.error(f"Fatal connection error: {e}")
            raise
        finally:
            self.cleanup()
        
    def onReceive(self, packet, interface): # called when a packet arrives
        """
        Handles incoming Meshtastic packets with improved error handling.
        Args:
            packet (bytes|dict|str): The received packet data (could be bytes, JSON string, or dict).
        """
        import json
        from meshtastic.protobuf import mesh_pb2
        import base64
        
        try:
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

            if not packet_dict:
                logging.warning("Failed to decode packet, skipping...")
                return

            self._update_cache_from_packet(packet_dict)
            
            # Update web interface with packet data
            self._update_web_interface(packet_dict)
            
            logging.info("Packet Received!")
            out_packet = {}
            for field_descriptor, field_value in packet_dict.items():
                out_packet[field_descriptor] = field_value

            # Get gateway ID safely
            try:
                interface = self.connection_manager.get_interface()
                if interface:
                    node_info = interface.getMyNodeInfo()
                    out_packet["gatewayId"] = node_info["user"]["id"]
                else:
                    logging.warning("No interface available, using cached gateway ID")
                    out_packet["gatewayId"] = getattr(self.connection_manager, 'connected_node_id', 'unknown')
            except Exception as e:
                logging.error(f"Error getting gateway ID: {e}")
                out_packet["gatewayId"] = getattr(self.connection_manager, 'connected_node_id', 'unknown')
            
            out_packet["source"] = "rf"

            self.publish_dict_to_mqtt(out_packet)
            
        except Exception as e:
            logging.error(f"Error processing received packet: {e}")
            # Don't let packet processing errors crash the application
    
    def publish_dict_to_mqtt(self, payload):
        """
        Publishes a dictionary payload to an MQTT topic with improved error handling.

        Args:
            payload (dict): The dictionary payload to publish.
        """
        try:
            if not self.mqtt_connected:
                logging.warning("MQTT not connected, attempting to reconnect...")
                try:
                    self.mqtt_client.reconnect()
                except Exception as e:
                    logging.error(f"Failed to reconnect to MQTT: {e}")
                    return
            
            topic_node = f"{self.topic}/{payload['fromId']}"
            payload_json = json.dumps(payload, default=str)
            
            # Publish the JSON payload to the specified topic
            result = self.mqtt_client.publish(topic_node, payload_json)
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logging.error(f"Failed to publish to MQTT: {result.rc}")
            else:
                logging.debug(f"Successfully published to {topic_node}")
                
        except Exception as e:
            logging.error(f"Error publishing to MQTT: {e}")
            # Don't let MQTT errors crash the application


if __name__ == "__main__":
    """Main entry point for the Meshtastic MQTT handler with improved error handling."""
    
    parser = argparse.ArgumentParser(description='Meshtastic MQTT Handler')
    parser.add_argument('--broker', default='mqtt.nhmesh.live', action=EnvDefault, envvar="MQTT_ENDPOINT", help='MQTT broker address')
    parser.add_argument('--port', default=1883, type=int, action=EnvDefault, envvar="MQTT_PORT", help='MQTT broker port')
    parser.add_argument('--topic', default='msh/US/NH/', action=EnvDefault, envvar="MQTT_TOPIC", help='Root topic')
    parser.add_argument('--tls', type=bool, default=False, help='Enable TLS/SSL')
    parser.add_argument('--username', action=EnvDefault, envvar="MQTT_USERNAME", help='MQTT username')
    parser.add_argument('--password', action=EnvDefault, envvar="MQTT_PASSWORD", help='MQTT password')
    parser.add_argument('--node-ip', action=EnvDefault, envvar="NODE_IP", help='Node IP address')
    parser.add_argument('--web-interface', action='store_true', default=True, help='Enable web interface (default: True)')
    parser.add_argument('--no-web-interface', dest='web_interface', action='store_false', help='Disable web interface')
    parser.add_argument('--web-host', default='0.0.0.0', action=EnvDefault, envvar="WEB_HOST", help='Web interface host')
    parser.add_argument('--web-port', default=5001, type=int, action=EnvDefault, envvar="WEB_PORT", help='Web interface port')
    args = parser.parse_args()

    # Set up signal handlers for graceful shutdown
    def signal_handler(signum, frame):
        logging.info(f"Received signal {signum}, shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    client = None
    try:
        logging.info("Starting Meshtastic MQTT Handler with improved resilience...")
        
        # Initialize the handler with retry logic
        max_init_attempts = 3
        for attempt in range(max_init_attempts):
            try:
                client = MeshtasticMQTTHandler(args.broker, args.port, args.topic, args.tls, args.username, args.password, args.node_ip)
                logging.info("Successfully initialized Meshtastic MQTT Handler")
                break
            except Exception as e:
                logging.error(f"Initialization attempt {attempt + 1}/{max_init_attempts} failed: {e}")
                if attempt < max_init_attempts - 1:
                    logging.info("Retrying initialization in 5 seconds...")
                    time.sleep(5)
                else:
                    logging.error("Max initialization attempts reached, exiting...")
                    sys.exit(1)
        
        # Configure web interface
        client.configure_web_interface(args.web_interface, args.web_host, args.web_port)
        
        # Give web interface a moment to start
        if args.web_interface:
            time.sleep(2)
            print(f"\n🌐 Web Interface: http://localhost:{args.web_port}")
            print("📊 Monitor your mesh network in real-time!")
            print("Press Ctrl+C to stop\n")
        
        # Start the main connection loop
        client.connect()
        
    except KeyboardInterrupt:
        logging.info("Received keyboard interrupt, shutting down...")
    except Exception as e:
        logging.error(f"Fatal error: {e}")
        import traceback
        logging.error(f"Traceback: {traceback.format_exc()}")
    finally:
        if client:
            try:
                client.cleanup()
            except Exception as e:
                logging.error(f"Error during cleanup: {e}")
        logging.info("Application shutdown complete")
        sys.exit(0)