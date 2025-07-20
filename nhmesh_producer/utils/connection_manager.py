"""
ConnectionManager for managing Meshtastic interface connections with automatic reconnection.
"""

import logging
import threading
import time
from typing import Any

import meshtastic
import meshtastic.tcp_interface
from pubsub import pub


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
        self.last_heartbeat = time.time()
        self.connection_errors = 0
        self.max_connection_errors = 10
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.node_info: dict[str, Any] | None = None
        self.connected_node_id: str | None = None
        self._meshtastic_connected = False  # Track connection state from pubsub events

        # Subscribe to Meshtastic connection events
        pub.subscribe(self._on_connection_established, "meshtastic.connection.established")
        pub.subscribe(self._on_connection_lost, "meshtastic.connection.lost")

        # Start health monitoring thread
        self.health_thread = threading.Thread(target=self._health_monitor, daemon=True)
        self.health_thread.start()

    def _on_connection_established(self, interface: Any) -> None:
        """Callback for when Meshtastic reports connection established"""
        if interface == self.interface:
            logging.info("[ConnectionManager] Pubsub: Connection established")
            self._meshtastic_connected = True
            self.connection_errors = 0

    def _on_connection_lost(self, interface: Any) -> None:
        """Callback for when Meshtastic reports connection lost"""
        if interface == self.interface:
            logging.warning("[ConnectionManager] Pubsub: Connection lost")
            self._meshtastic_connected = False
            self.connection_errors += 1

    def connect(self) -> bool:
        """Establish connection to Meshtastic node with error handling"""
        with self.lock:
            try:
                if self.interface:
                    try:
                        self.interface.close()
                    except Exception as e:
                        logging.warning(f"[ConnectionManager] Error closing existing interface: {e}")

                logging.info(f"[ConnectionManager] Connecting to Meshtastic node at {self.node_ip}")
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

                self.connection_errors = 0
                self.last_heartbeat = time.time()
                self._meshtastic_connected = True  # Will be confirmed by pubsub event

                logging.info(f"[ConnectionManager] Successfully connected to node {self.connected_node_id}")
                logging.info(f"[ConnectionManager] Connection state: errors={self.connection_errors}")
                return True

            except Exception as e:
                logging.warning(f"[ConnectionManager] Failed to connect to Meshtastic node: {e}")
                self.connection_errors += 1
                self._meshtastic_connected = False
                logging.info(f"[ConnectionManager] Connection failed - errors={self.connection_errors}")
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
            logging.info(f"[ConnectionManager] Reconnection attempt {attempts}/{self.reconnect_attempts}")

            if self.connect():
                return True

            # Check if shutdown was requested
            if self.stop_event.is_set():
                logging.info("[ConnectionManager] Shutdown requested during reconnection, aborting")
                break

            # Exponential backoff with interruptible wait
            delay = self.reconnect_delay * (2 ** (attempts - 1))
            logging.info(
                f"[ConnectionManager] Reconnection failed, waiting {delay} seconds before next attempt"
            )

            # Use interruptible wait instead of time.sleep
            if self.stop_event.wait(timeout=delay):
                logging.info("[ConnectionManager] Shutdown requested during reconnection delay, aborting")
                break

        if self.stop_event.is_set():
            logging.info("[ConnectionManager] Reconnection aborted due to shutdown")
        else:
            logging.error("[ConnectionManager] Max reconnection attempts reached")
        return False

    def _health_monitor(self) -> None:
        """Monitor connection health and trigger reconnection if needed"""
        logging.info(f"[ConnectionManager] Health monitor starting with {self.health_check_interval}s interval")
        while not self.stop_event.is_set():
            try:
                # Use wait() instead of sleep() so it's interruptible
                if self.stop_event.wait(timeout=self.health_check_interval):
                    # Event was set (shutdown requested), exit gracefully
                    logging.info("[ConnectionManager] Health monitor received shutdown signal, exiting")
                    break

                # Only continue if not shutting down
                if self.stop_event.is_set():
                    break

                logging.info(f"[ConnectionManager] Health monitor running check - connected: {self.is_connected()}, errors: {self.connection_errors}/{self.max_connection_errors}")

                if (
                    not self.is_connected()
                    or self.connection_errors >= self.max_connection_errors
                ):
                    logging.warning(
                        f"[ConnectionManager] Connection health check failed - connected: {self.is_connected()}, errors: {self.connection_errors}, attempting reconnection"
                    )
                    # Don't attempt reconnection if shutting down
                    if not self.stop_event.is_set():
                        self.reconnect()

                # Check if interface is still responsive
                if self.interface and self.is_connected() and not self.stop_event.is_set():
                    try:
                        logging.info("[ConnectionManager] Performing interface responsiveness check...")
                        # Simple health check - try to get node info (pubsub will handle disconnect events)
                        self.interface.getMyNodeInfo()
                        self.last_heartbeat = time.time()
                        logging.info("[ConnectionManager] Health check passed - interface responsive")
                    except (BrokenPipeError, ConnectionResetError, OSError) as e:
                        logging.warning(f"[ConnectionManager] Connection lost during health check: {e}")
                        self.connection_errors += 1
                        self._meshtastic_connected = False
                        # Force close the interface to clean up internal threads
                        try:
                            self.interface.close()
                        except Exception:
                            pass
                        self.interface = None
                    except Exception as e:
                        logging.warning(f"[ConnectionManager] Health check failed: {e}")
                        self.connection_errors += 1
                else:
                    if not self.interface:
                        logging.info("[ConnectionManager] Health check skipped - no interface")
                    elif not self.is_connected():
                        logging.info("[ConnectionManager] Health check skipped - not connected")
                    else:
                        logging.info("[ConnectionManager] Health check skipped - shutdown requested")

            except Exception as e:
                logging.error(f"[ConnectionManager] Error in health monitor: {e}")

        logging.info("[ConnectionManager] Health monitor thread exiting cleanly")

    def is_connected(self) -> bool:
        """Check if currently connected using Meshtastic pubsub events"""
        if not self.interface:
            return False

        # Use pubsub connection state as primary source of truth
        connected = self._meshtastic_connected
        logging.info(f"[ConnectionManager] is_connected() = {connected} (interface exists, pubsub_connected={connected})")
        return connected

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
            logging.warning("[ConnectionManager] Interface not connected, attempting reconnection...")
            if not self.reconnect():
                logging.error("[ConnectionManager] Interface reconnection failed, no interface available")
                return None

        # Do a quick responsiveness check before returning the interface
        try:
            if self.interface:
                self.interface.getMyNodeInfo()
                return self.interface
        except (BrokenPipeError, ConnectionResetError, OSError) as e:
            logging.warning(f"[ConnectionManager] Interface became unresponsive during check: {e}")
            self.connection_errors += 1
            # Force close the interface to clean up internal threads
            try:
                self.interface.close()
            except Exception:
                pass
            self.interface = None

            # Try to reconnect immediately
            logging.warning("[ConnectionManager] Attempting immediate reconnection after interface failure...")
            if self.reconnect():
                return self.interface
            else:
                logging.error("[ConnectionManager] Immediate reconnection failed")
                return None
        except Exception as e:
            logging.warning(f"[ConnectionManager] Interface check failed with unexpected error: {e}")
            self.connection_errors += 1
            return None

        return self.interface

    def notify_connection_error(self, error: Exception) -> None:
        """
        Notify the connection manager of a connection error that occurred during operations.
        This allows immediate detection of connection issues rather than waiting for health checks.

        Args:
            error: The exception that occurred during the operation
        """
        if isinstance(error, BrokenPipeError | ConnectionResetError | OSError):
            logging.warning(f"[ConnectionManager] Connection error reported: {error}")
            self.connection_errors += 1
            self._meshtastic_connected = False
            # Force close the interface to clean up internal threads
            if self.interface:
                try:
                    self.interface.close()
                except Exception:
                    pass
                self.interface = None
        else:
            logging.info(f"[ConnectionManager] Non-connection error reported: {error}")

    def close(self) -> None:
        """Close the connection and stop monitoring"""
        logging.info("[ConnectionManager] ConnectionManager closing...")
        self.stop_event.set()

        # Unsubscribe from pubsub events
        try:
            pub.unsubscribe(self._on_connection_established, "meshtastic.connection.established")
            pub.unsubscribe(self._on_connection_lost, "meshtastic.connection.lost")
            logging.info("[ConnectionManager] Unsubscribed from pubsub events")
        except Exception as e:
            logging.warning(f"[ConnectionManager] Error unsubscribing from pubsub: {e}")

        # Wait for health monitor thread to finish
        if hasattr(self, "health_thread") and self.health_thread.is_alive():
            logging.info("[ConnectionManager] Waiting for health monitor thread to finish...")
            self.health_thread.join(timeout=2.0)  # 2 second timeout
            if self.health_thread.is_alive():
                logging.warning("[ConnectionManager] Health monitor thread did not finish cleanly")
            else:
                logging.info("[ConnectionManager] Health monitor thread finished cleanly")

        if self.interface:
            try:
                self.interface.close()
                logging.info("[ConnectionManager] Interface closed successfully")
            except Exception as e:
                logging.error(f"[ConnectionManager] Error closing interface during shutdown: {e}")
