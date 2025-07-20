"""
ConnectionManager for managing Meshtastic interface connections with automatic reconnection.
"""

import logging
import select
import socket
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

    def _is_socket_connected(self, sock: socket.socket) -> bool:
        """
        Check if socket is still connected using direct socket inspection.
        This is much faster and more reliable than the library's internal checks.

        Based on solution from: https://github.com/meshtastic/python/issues/765#issuecomment-2817305288
        """
        try:
            # Use select to check if socket has data available for reading
            r, _, _ = select.select([sock], [], [], 0)
            if r:
                # Socket has data, peek at it without consuming
                data = sock.recv(1, socket.MSG_PEEK)
                if not data:
                    # Empty data means connection closed
                    return False
            # Socket is connected (either no data pending or data available)
            return True
        except OSError:
            # Any socket error means disconnected
            return False

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

                logging.info(f"[ConnectionManager] Successfully connected to node {self.connected_node_id}")
                logging.info(f"[ConnectionManager] Connection state: errors={self.connection_errors}")
                return True

            except Exception as e:
                logging.warning(f"[ConnectionManager] Failed to connect to Meshtastic node: {e}")
                self.connection_errors += 1
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
        """Monitor connection health using direct socket inspection and trigger reconnection if needed"""
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

                # Check socket-level connection health
                socket_connected = False
                meshtastic_connected = False
                if self.interface:
                    if hasattr(self.interface, 'socket'):
                        socket_connected = self._is_socket_connected(self.interface.socket)
                    if hasattr(self.interface, 'isConnected'):
                        meshtastic_connected = self.interface.isConnected.is_set()

                logging.info(f"[ConnectionManager] Health monitor check - socket_connected: {socket_connected}, meshtastic_connected: {meshtastic_connected}, errors: {self.connection_errors}/{self.max_connection_errors}")

                # Disconnect detected at socket level
                if self.interface and not socket_connected:
                    logging.warning("[ConnectionManager] Socket-level disconnect detected, marking connection as lost")
                    self.connection_errors += 1
                    # Force close the interface to clean up internal threads
                    try:
                        self.interface.close()
                    except Exception:
                        pass
                    self.interface = None

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

            except Exception as e:
                logging.error(f"[ConnectionManager] Error in health monitor: {e}")

        logging.info("[ConnectionManager] Health monitor thread exiting cleanly")

    def is_connected(self) -> bool:
        """Check if currently connected using both socket-level and Meshtastic library state"""
        if not self.interface:
            return False

        # Check socket-level connection health first (fast and reliable)
        socket_connected = False
        if hasattr(self.interface, 'socket'):
            socket_connected = self._is_socket_connected(self.interface.socket)

        # Check Meshtastic library connection state
        meshtastic_connected = False
        if hasattr(self.interface, 'isConnected'):
            meshtastic_connected = self.interface.isConnected.is_set()

        # Both socket and library must agree on connection state
        connected = socket_connected and meshtastic_connected
        logging.info(f"[ConnectionManager] is_connected() = {connected} (socket={socket_connected}, meshtastic={meshtastic_connected})")
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

        # Do a quick socket-level check before returning the interface
        if self.interface and hasattr(self.interface, 'socket'):
            if not self._is_socket_connected(self.interface.socket):
                logging.warning("[ConnectionManager] Interface socket disconnected during check")
                self.connection_errors += 1
                # Force close the interface to clean up internal threads
                try:
                    self.interface.close()
                except Exception:
                    pass
                self.interface = None

                # Try to reconnect immediately
                logging.warning("[ConnectionManager] Attempting immediate reconnection after socket failure...")
                if self.reconnect():
                    return self.interface
                else:
                    logging.error("[ConnectionManager] Immediate reconnection failed")
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
