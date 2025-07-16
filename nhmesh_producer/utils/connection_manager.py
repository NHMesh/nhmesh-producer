"""
ConnectionManager for managing Meshtastic interface connections with automatic reconnection.
"""

import logging
import time
import threading
import meshtastic
import meshtastic.tcp_interface


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
