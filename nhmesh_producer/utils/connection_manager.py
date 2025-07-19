"""
ConnectionManager for managing Meshtastic interface connections with automatic reconnection.
"""

import logging
import threading
import time
from typing import Any

import meshtastic
import meshtastic.tcp_interface


class ConnectionManager:
    """Manages connection health and automatic reconnection for Meshtastic interface"""

    def __init__(
        self,
        node_ip: str,
        reconnect_attempts: int = 5,
        reconnect_delay: int = 5,
        health_check_interval: int = 10,  # Reduced from 30 to detect issues faster
    ) -> None:
        self.node_ip = node_ip
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.health_check_interval = health_check_interval
        self.interface: Any = None
        self.connected = False
        self.last_heartbeat = time.time()
        self.connection_errors = 0
        self.max_connection_errors = 10
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.node_info: dict[str, Any] | None = None
        self.connected_node_id: str | None = None

        # Start health monitoring thread
        self.health_thread = threading.Thread(target=self._health_monitor, daemon=True)
        self.health_thread.start()

    def connect(self) -> bool:
        """Establish connection to Meshtastic node with error handling"""
        with self.lock:
            try:
                if self.interface:
                    try:
                        self.interface.close()
                    except Exception as e:
                        logging.warning(f"Error closing existing interface: {e}")

                logging.info(f"Connecting to Meshtastic node at {self.node_ip}")
                self.interface = meshtastic.tcp_interface.TCPInterface(
                    hostname=self.node_ip
                )

                # Test connection by getting node info
                self.node_info = self.interface.getMyNodeInfo()
                if self.node_info is None:
                    raise Exception(
                        "Failed to get node info - connection may be invalid"
                    )
                self.connected_node_id = self.node_info["user"]["id"]

                self.connected = True
                self.connection_errors = 0
                self.last_heartbeat = time.time()

                logging.info(f"Successfully connected to node {self.connected_node_id}")
                return True

            except Exception as e:
                logging.warning(f"Failed to connect to Meshtastic node: {e}")
                self.connected = False
                self.connection_errors += 1
                # Clean up any partially created interface
                if self.interface:
                    try:
                        self.interface.close()
                    except Exception:
                        pass
                    self.interface = None
                return False

    def reconnect(self) -> bool:
        """Attempt to reconnect with exponential backoff"""
        attempts = 0
        while attempts < self.reconnect_attempts and not self.stop_event.is_set():
            attempts += 1
            logging.info(f"Reconnection attempt {attempts}/{self.reconnect_attempts}")

            if self.connect():
                return True

            # Check if shutdown was requested
            if self.stop_event.is_set():
                logging.info("Shutdown requested during reconnection, aborting")
                break

            # Exponential backoff with interruptible wait
            delay = self.reconnect_delay * (2 ** (attempts - 1))
            logging.info(
                f"Reconnection failed, waiting {delay} seconds before next attempt"
            )

            # Use interruptible wait instead of time.sleep
            if self.stop_event.wait(timeout=delay):
                logging.info("Shutdown requested during reconnection delay, aborting")
                break

        if self.stop_event.is_set():
            logging.info("Reconnection aborted due to shutdown")
        else:
            logging.error("Max reconnection attempts reached")
        return False

    def _health_monitor(self) -> None:
        """Monitor connection health and trigger reconnection if needed"""
        while not self.stop_event.is_set():
            try:
                # Use wait() instead of sleep() so it's interruptible
                if self.stop_event.wait(timeout=self.health_check_interval):
                    # Event was set (shutdown requested), exit gracefully
                    logging.info("Health monitor received shutdown signal, exiting")
                    break

                # Only continue if not shutting down
                if self.stop_event.is_set():
                    break

                if (
                    not self.connected
                    or self.connection_errors >= self.max_connection_errors
                ):
                    logging.warning(
                        "Connection health check failed, attempting reconnection"
                    )
                    # Don't attempt reconnection if shutting down
                    if not self.stop_event.is_set():
                        self.reconnect()

                # Check if interface is still responsive
                if self.interface and self.connected and not self.stop_event.is_set():
                    try:
                        # Simple health check - try to get node info
                        self.interface.getMyNodeInfo()
                        self.last_heartbeat = time.time()
                        logging.debug("Health check passed")
                    except (BrokenPipeError, ConnectionResetError, OSError) as e:
                        logging.warning(f"Connection lost during health check: {e}")
                        self.connected = False
                        self.connection_errors += 1
                        # Force close the interface to clean up internal threads
                        try:
                            self.interface.close()
                        except Exception:
                            pass
                        self.interface = None
                    except Exception as e:
                        logging.warning(f"Health check failed: {e}")
                        self.connected = False
                        self.connection_errors += 1

            except Exception as e:
                logging.error(f"Error in health monitor: {e}")

        logging.info("Health monitor thread exiting cleanly")

    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.connected and self.interface is not None

    def get_interface(self) -> Any | None:
        """Get the current interface, reconnecting if necessary"""
        if not self.is_connected():
            if not self.reconnect():
                return None
        return self.interface

    def get_ready_interface(self) -> Any | None:
        """
        Get an interface that's ready for operations.

        Returns:
            The interface if available and connected, None if unavailable
        """
        if not self.is_connected():
            logging.info("Interface not connected, attempting reconnection...")
            if not self.reconnect():
                logging.warning("Interface reconnection failed, no interface available")
                return None

        return self.interface

    def close(self) -> None:
        """Close the connection and stop monitoring"""
        logging.info("ConnectionManager closing...")
        self.stop_event.set()

        # Wait for health monitor thread to finish
        if hasattr(self, "health_thread") and self.health_thread.is_alive():
            logging.info("Waiting for health monitor thread to finish...")
            self.health_thread.join(timeout=2.0)  # 2 second timeout
            if self.health_thread.is_alive():
                logging.warning("Health monitor thread did not finish cleanly")
            else:
                logging.info("Health monitor thread finished cleanly")

        if self.interface:
            try:
                self.interface.close()
                logging.info("Interface closed successfully")
            except Exception as e:
                logging.error(f"Error closing interface during shutdown: {e}")
        self.connected = False
