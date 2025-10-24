"""
Web interface for nhmesh-producer with health monitoring and stats API.
"""

import logging
import threading
import time
from datetime import datetime
from typing import Any

from flask import Flask, jsonify, render_template_string

# Simple HTML template for the dashboard
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>NHMesh Producer - Status Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { 
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: #f5f5f5;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 30px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .card {
            background: white;
            padding: 20px;
            margin-bottom: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .status { display: inline-block; padding: 5px 15px; border-radius: 20px; font-weight: bold; }
        .status.connected { background: #10b981; color: white; }
        .status.disconnected { background: #ef4444; color: white; }
        .status.reconnecting { background: #f59e0b; color: white; }
        .metric { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #eee; }
        .metric:last-child { border-bottom: none; }
        .metric-label { font-weight: 600; color: #666; }
        .metric-value { color: #333; }
        h2 { margin-top: 0; color: #333; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .refresh-info { text-align: center; color: #666; margin-top: 10px; }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.5; } }
        .pulsing { animation: pulse 2s ease-in-out infinite; }
    </style>
    <script>
        function refreshStats() {
            fetch('/api/stats')
                .then(response => response.json())
                .then(data => {
                    document.getElementById('stats-data').textContent = JSON.stringify(data, null, 2);
                    document.getElementById('last-update').textContent = new Date().toLocaleTimeString();
                })
                .catch(error => console.error('Error fetching stats:', error));
        }
        
        // Auto-refresh every 5 seconds
        setInterval(refreshStats, 5000);
        
        // Initial load
        window.addEventListener('load', refreshStats);
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🛰️ NHMesh Producer</h1>
            <p>Meshtastic to MQTT Bridge - Status Dashboard</p>
        </div>
        
        <div class="card">
            <h2>System Status</h2>
            <div class="metric">
                <span class="metric-label">Producer Status:</span>
                <span class="status {{ status_class }}">{{ status_text }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Meshtastic Connection:</span>
                <span class="metric-value">{{ meshtastic_status }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">MQTT Connection:</span>
                <span class="metric-value">{{ mqtt_status }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Uptime:</span>
                <span class="metric-value">{{ uptime }}</span>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h2>Connection Info</h2>
                <div class="metric">
                    <span class="metric-label">Node IP:</span>
                    <span class="metric-value">{{ node_ip }}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">MQTT Broker:</span>
                    <span class="metric-value">{{ mqtt_broker }}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Topic:</span>
                    <span class="metric-value">{{ mqtt_topic }}</span>
                </div>
            </div>
            
            <div class="card">
                <h2>Statistics</h2>
                <div class="metric">
                    <span class="metric-label">Packets Published:</span>
                    <span class="metric-value">{{ packets_published }}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Last Packet:</span>
                    <span class="metric-value">{{ last_packet_time }}</span>
                </div>
                <div class="metric">
                    <span class="metric-label">Connection Errors:</span>
                    <span class="metric-value">{{ connection_errors }}</span>
                </div>
            </div>
        </div>
        
        <div class="card">
            <h2>Live Stats API Response <span class="pulsing">●</span></h2>
            <pre id="stats-data" style="background: #f8f9fa; padding: 15px; border-radius: 5px; overflow-x: auto;">Loading...</pre>
            <div class="refresh-info">Last updated: <span id="last-update">Never</span> (auto-refresh every 5s)</div>
        </div>
    </div>
</body>
</html>
"""


class WebInterface:
    """Web interface for monitoring nhmesh-producer health and stats"""

    def __init__(self, handler: Any, host: str = "0.0.0.0", port: int = 5001):
        """
        Initialize the web interface.

        Args:
            handler: MeshtasticMQTTHandler instance
            host: Host to bind to (default: 0.0.0.0 for Docker)
            port: Port to listen on (default: 5001)
        """
        self.handler = handler
        self.host = host
        self.port = port
        self.app = Flask(__name__)
        self.start_time = time.time()
        self.packets_published = 0
        self.last_packet_time: float | None = None
        self.server_thread: threading.Thread | None = None

        # Setup routes
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup Flask routes"""

        @self.app.route("/")
        def index():
            """Main dashboard page"""
            # Get connection status
            meshtastic_connected = self.handler.connection_manager.is_connected()
            mqtt_connected = getattr(self.handler, "mqtt_connected", False)

            # Determine overall status
            if meshtastic_connected and mqtt_connected:
                status_text = "CONNECTED"
                status_class = "connected"
            elif self.handler.connection_manager.reconnecting:
                status_text = "RECONNECTING"
                status_class = "reconnecting"
            else:
                status_text = "DISCONNECTED"
                status_class = "disconnected"

            # Calculate uptime
            uptime_seconds = int(time.time() - self.start_time)
            uptime_hours = uptime_seconds // 3600
            uptime_minutes = (uptime_seconds % 3600) // 60
            uptime_str = f"{uptime_hours}h {uptime_minutes}m"

            # Last packet time
            if self.last_packet_time:
                last_packet_str = datetime.fromtimestamp(self.last_packet_time).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                last_packet_str = "Never"

            connection_info = self.handler.connection_manager.get_connection_info()

            return render_template_string(
                DASHBOARD_TEMPLATE,
                status_text=status_text,
                status_class=status_class,
                meshtastic_status="Connected" if meshtastic_connected else "Disconnected",
                mqtt_status="Connected" if mqtt_connected else "Disconnected",
                uptime=uptime_str,
                node_ip=self.handler.node_ip or "N/A",
                mqtt_broker=f"{self.handler.broker}:{self.handler.port}",
                mqtt_topic=self.handler.topic,
                packets_published=self.packets_published,
                last_packet_time=last_packet_str,
                connection_errors=connection_info.get("connection_errors", 0),
            )

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
            """Simple health check endpoint (Docker healthcheck compatible)"""
            is_healthy = self.handler.connection_manager.is_connected()

            if is_healthy:
                return jsonify({"status": "healthy", "timestamp": time.time()}), 200
            else:
                return (
                    jsonify(
                        {
                            "status": "unhealthy",
                            "timestamp": time.time(),
                            "reason": "Meshtastic not connected",
                        }
                    ),
                    503,
                )

        @self.app.route("/api/connection")
        def connection():
            """Detailed connection information endpoint"""
            return jsonify(self.handler.connection_manager.get_connection_info())

    def increment_packet_count(self) -> None:
        """Increment the packet counter (call this when packet is published)"""
        self.packets_published += 1
        self.last_packet_time = time.time()

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


