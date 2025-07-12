import logging
import json
import threading
import time
from datetime import datetime, timezone
from flask import Flask, render_template, jsonify
import paho.mqtt.client as mqtt
from collections import defaultdict, deque
import argparse
from utils.envdefault import EnvDefault

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)

class TelemetryWebInterface:
    def __init__(self, broker, port, topic, username, password):
        self.broker = broker
        self.port = port
        self.topic = topic
        self.username = username
        self.password = password
        
        # Data storage
        self.nodes = defaultdict(dict)  # node_id -> node_data
        self.recent_packets = deque(maxlen=1000)  # Last 1000 packets
        self.network_stats = {
            'total_packets': 0,
            'active_nodes': 0,
            'last_update': None
        }
        
        # MQTT client setup
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.username_pw_set(username=self.username, password=self.password)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.on_disconnect = self.on_disconnect
        
        # Start MQTT connection in background thread
        self.mqtt_thread = threading.Thread(target=self._mqtt_loop, daemon=True)
        self.mqtt_thread.start()
        
        # Start stats update thread
        self.stats_thread = threading.Thread(target=self._update_stats, daemon=True)
        self.stats_thread.start()
    
    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            logging.info("Connected to MQTT broker")
            # Subscribe to all topics under the root topic
            client.subscribe(f"{self.topic}/#")
        else:
            logging.error(f"Failed to connect to MQTT broker with code {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        logging.warning(f"Disconnected from MQTT broker with code {rc}")
        if rc != 0:
            logging.info("Attempting to reconnect...")
            time.sleep(5)
            try:
                client.reconnect()
            except Exception as e:
                logging.error(f"Reconnection failed: {e}")
    
    def on_message(self, client, userdata, msg):
        try:
            # Parse the packet
            packet = json.loads(msg.payload.decode('utf-8'))
            
            # Extract node ID from topic or packet
            node_id = packet.get('fromId') or packet.get('from_id_str')
            if not node_id:
                return
            
            # Update node data
            self._update_node_data(node_id, packet)
            
            # Add to recent packets
            packet['received_at'] = datetime.now(timezone.utc).isoformat()
            self.recent_packets.append(packet)
            
            # Update stats
            self.network_stats['total_packets'] += 1
            self.network_stats['last_update'] = datetime.now(timezone.utc).isoformat()
            
        except Exception as e:
            logging.error(f"Error processing message: {e}")
    
    def _update_node_data(self, node_id, packet):
        """Update node information with latest packet data"""
        node_data = self.nodes[node_id]
        
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
    
    def _mqtt_loop(self):
        """MQTT client loop in background thread"""
        try:
            self.mqtt_client.connect(self.broker, self.port, 60)
            self.mqtt_client.loop_forever()
        except Exception as e:
            logging.error(f"MQTT loop error: {e}")
    
    def _update_stats(self):
        """Update network statistics periodically"""
        while True:
            try:
                # Count active nodes (seen in last 10 minutes)
                cutoff_time = datetime.now(timezone.utc).timestamp() - 600
                active_nodes = 0
                
                for node_data in self.nodes.values():
                    if 'last_seen' in node_data:
                        last_seen = datetime.fromisoformat(node_data['last_seen'].replace('Z', '+00:00'))
                        if last_seen.timestamp() > cutoff_time:
                            active_nodes += 1
                
                self.network_stats['active_nodes'] = active_nodes
                time.sleep(30)  # Update every 30 seconds
                
            except Exception as e:
                logging.error(f"Stats update error: {e}")
                time.sleep(30)

@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('dashboard.html')

@app.route('/api/nodes')
def get_nodes():
    """API endpoint to get all nodes data"""
    if not hasattr(app, 'telemetry_interface') or app.telemetry_interface is None:
        return jsonify({'error': 'Telemetry interface not initialized'}), 500
    
    nodes_data = {}
    for node_id, node_data in app.telemetry_interface.nodes.items():
        nodes_data[node_id] = node_data
    
    return jsonify(nodes_data)

@app.route('/api/recent_packets')
def get_recent_packets():
    """API endpoint to get recent packets"""
    if not hasattr(app, 'telemetry_interface') or app.telemetry_interface is None:
        return jsonify({'error': 'Telemetry interface not initialized'}), 500
    
    return jsonify(list(app.telemetry_interface.recent_packets))

@app.route('/api/stats')
def get_stats():
    """API endpoint to get network statistics"""
    if not hasattr(app, 'telemetry_interface') or app.telemetry_interface is None:
        return jsonify({'error': 'Telemetry interface not initialized'}), 500
    
    return jsonify(app.telemetry_interface.network_stats)

@app.route('/api/node/<node_id>')
def get_node(node_id):
    """API endpoint to get specific node data"""
    if not hasattr(app, 'telemetry_interface') or app.telemetry_interface is None:
        return jsonify({'error': 'Telemetry interface not initialized'}), 500
    
    node_data = app.telemetry_interface.nodes.get(node_id)
    if node_data is None:
        return jsonify({'error': 'Node not found'}), 404
    
    return jsonify(node_data)

# This module is designed to be imported and used by the startup script
# See start_web_interface.py for the main entry point 