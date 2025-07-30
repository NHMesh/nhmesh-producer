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
        health_check_interval: int = 10,  # Back to 10 seconds since events handle immediate detection
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
        self.last_successful_health_check = time.time()

        # Start health monitoring thread
        self.health_thread = threading.Thread(target=self._health_monitor, daemon=True)
        self.health_thread.start()

    def connect(self, skip_lock: bool = False) -> bool:
        """Establish connection to Meshtastic node with error handling"""
        logging.info(f"connect() called with skip_lock={skip_lock}")
        if skip_lock:
            # Direct connection without lock (for health monitor thread)
            try:
                if self.interface:
                    try:
                        logging.info("Closing existing interface...")
                        self.interface.close()
                        logging.info("Existing interface closed")
                    except Exception as e:
                        logging.warning(f"Error closing existing interface: {e}")

                logging.info(f"Connecting to Meshtastic node at {self.node_ip}")
                self.interface = meshtastic.tcp_interface.TCPInterface(
                    hostname=self.node_ip
                )
                logging.info("TCPInterface created successfully")

                # Test connection by getting node info
                logging.info("Testing connection by calling getMyNodeInfo()...")
                self.node_info = self.interface.getMyNodeInfo()
                logging.info(f"getMyNodeInfo() returned: {self.node_info}")
                if self.node_info is None:
                    raise Exception(
                        "Failed to get node info - connection may be invalid"
                    )
                self.connected_node_id = self.node_info["user"]["id"]

                self.connected = True
                self.connection_errors = 0
                self.last_heartbeat = time.time()
                self.last_successful_health_check = (
                    time.time()
                )  # Update last successful check on successful connection

                logging.info(f"Successfully connected to node {self.connected_node_id}")
                return True

            except Exception as e:
                logging.error(f"Failed to connect to Meshtastic node: {e}")
                self.connected = False
                self.connection_errors += 1
                return False
        else:
            # Normal connection with lock
            with self.lock:
                try:
                    if self.interface:
                        try:
                            logging.info("Closing existing interface...")
                            self.interface.close()
                            logging.info("Existing interface closed")
                        except Exception as e:
                            logging.warning(f"Error closing existing interface: {e}")

                    logging.info(f"Connecting to Meshtastic node at {self.node_ip}")
                    self.interface = meshtastic.tcp_interface.TCPInterface(
                        hostname=self.node_ip
                    )
                    logging.info("TCPInterface created successfully")

                    # Test connection by getting node info
                    logging.info("Testing connection by calling getMyNodeInfo()...")
                    self.node_info = self.interface.getMyNodeInfo()
                    logging.info(f"getMyNodeInfo() returned: {self.node_info}")
                    if self.node_info is None:
                        raise Exception(
                            "Failed to get node info - connection may be invalid"
                        )
                    self.connected_node_id = self.node_info["user"]["id"]

                    self.connected = True
                    self.connection_errors = 0
                    self.last_heartbeat = time.time()
                    self.last_successful_health_check = (
                        time.time()
                    )  # Update last successful check on successful connection

                    logging.info(
                        f"Successfully connected to node {self.connected_node_id}"
                    )
                    return True

                except Exception as e:
                    logging.error(f"Failed to connect to Meshtastic node: {e}")
                    self.connected = False
                    self.connection_errors += 1
                    return False

    def reconnect(self, skip_lock: bool = False) -> bool:
        """Attempt to reconnect with exponential backoff"""
        logging.info(f"reconnect() called with skip_lock={skip_lock}")
        attempts = 0
        while attempts < self.reconnect_attempts and not self.stop_event.is_set():
            attempts += 1
            logging.info(f"Reconnection attempt {attempts}/{self.reconnect_attempts}")

            logging.info("Calling connect() from reconnect()...")
            if self.connect(skip_lock=skip_lock):
                logging.info("connect() succeeded, reconnection successful")
                return True
            else:
                logging.warning("connect() failed")

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
        logging.info(
            f"Health monitor started with {self.health_check_interval}s interval"
        )
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

                logging.info("=== HEALTH MONITOR CYCLE START ===")

                # Check connection status with proper locking
                should_reconnect = False
                with self.lock:
                    current_connected = self.connected
                    current_errors = self.connection_errors
                    current_max_errors = self.max_connection_errors
                    interface_exists = self.interface is not None
                    time_since_last_success = (
                        time.time() - self.last_successful_health_check
                    )

                    if (
                        not self.connected
                        or self.connection_errors >= self.max_connection_errors
                        or time_since_last_success
                        > 30  # Force reconnect if no successful check in 30 seconds
                    ):
                        should_reconnect = True

                logging.info(
                    f"Health check status: connected={current_connected}, errors={current_errors}/{current_max_errors}, interface_exists={interface_exists}, should_reconnect={should_reconnect}, time_since_last_success={time_since_last_success:.1f}s"
                )

                if should_reconnect:
                    if time_since_last_success > 30:
                        logging.warning(
                            f"Connection health check failed - no successful check in {time_since_last_success:.1f}s, forcing reconnection"
                        )
                    else:
                        logging.warning(
                            f"Connection health check failed (connected={current_connected}, errors={current_errors}), attempting reconnection"
                        )
                    # Don't attempt reconnection if shutting down
                    if not self.stop_event.is_set():
                        logging.info("Calling reconnect() from health monitor...")
                        self.reconnect(skip_lock=True)
                        logging.info("reconnect() call completed")

                # Always check interface health if we have an interface, regardless of connected state
                if self.interface and not self.stop_event.is_set():
                    logging.info("Interface exists, performing health check...")
                    try:
                        # Use threading-based timeout for health check
                        import threading

                        class HealthCheckResult:
                            def __init__(self):
                                self.success: bool = False
                                self.exception: Exception | None = None

                        result = HealthCheckResult()

                        def health_check():
                            nonlocal result
                            try:
                                logging.info("Health check: calling getMyNodeInfo()...")
                                node_info = self.interface.getMyNodeInfo()
                                logging.info(
                                    f"Health check: getMyNodeInfo() returned: {node_info}"
                                )
                                if node_info is None:
                                    raise Exception("getMyNodeInfo returned None")

                                # Additional check: verify the interface socket is still valid
                                if (
                                    hasattr(self.interface, "socket")
                                    and self.interface.socket
                                ):
                                    try:
                                        # Try to get socket info to verify it's still connected
                                        socket_info = self.interface.socket.getsockopt(
                                            1, 1
                                        )  # SOL_SOCKET, SO_ERROR
                                        if socket_info != 0:
                                            raise Exception(
                                                f"Socket error detected: {socket_info}"
                                            )
                                        logging.info("Socket health check passed")
                                    except Exception as socket_e:
                                        logging.warning(
                                            f"Socket health check failed: {socket_e}"
                                        )
                                        raise Exception(
                                            f"Socket connection broken: {socket_e}"
                                        ) from socket_e

                                result.success = True  # noqa: B023
                                logging.info("Health check: getMyNodeInfo() succeeded")
                            except Exception as e:
                                logging.error(
                                    f"Health check: getMyNodeInfo() failed with exception: {e}"
                                )
                                result.exception = e  # noqa: B023

                        # Run health check in separate thread with timeout
                        health_thread = threading.Thread(
                            target=health_check, daemon=True
                        )
                        logging.info("Starting health check thread...")
                        health_thread.start()
                        health_thread.join(
                            timeout=5
                        )  # Reduced timeout to 5 seconds for faster detection

                        if health_thread.is_alive():
                            # Thread is still running, timeout occurred
                            logging.warning("Health check timed out after 5 seconds")
                            raise TimeoutError("Health check timed out after 5 seconds")

                        logging.info(
                            f"Health check result: success={result.success}, exception={result.exception}"
                        )

                        if result.success:
                            # Update last heartbeat and reset errors on success
                            with self.lock:
                                self.last_heartbeat = time.time()
                                self.connection_errors = 0
                                self.connected = True  # Ensure connected state is set
                                self.last_successful_health_check = time.time()  # Update last successful check on successful health check
                            logging.info(
                                "Health check passed successfully, reset errors and updated heartbeat"
                            )
                        else:
                            # Health check failed
                            if result.exception is not None:
                                logging.error(
                                    f"Health check failed with exception: {result.exception}"
                                )
                                raise result.exception
                            else:
                                logging.error("Health check failed with unknown error")
                                raise Exception("Health check failed")

                    except (Exception, TimeoutError) as e:
                        logging.warning(f"Health check failed: {e}")
                        with self.lock:
                            self.connected = False
                            self.connection_errors += 1

                        # Immediately trigger reconnection on health check failure
                        if not self.stop_event.is_set():
                            logging.info(
                                "Health check failed, triggering immediate reconnection"
                            )
                            self.reconnect(skip_lock=True)
                elif not self.interface and not self.stop_event.is_set():
                    # No interface exists, try to reconnect
                    logging.warning("No interface exists, attempting reconnection")
                    with self.lock:
                        self.connected = False
                        self.connection_errors += 1

                    if not self.stop_event.is_set():
                        self.reconnect(skip_lock=True)
                else:
                    logging.info(
                        "Skipping health check - interface doesn't exist or shutdown requested"
                    )

                logging.info("=== HEALTH MONITOR CYCLE END ===")

            except Exception as e:
                logging.error(f"Error in health monitor: {e}")
                # Don't let exceptions kill the health monitor thread
                time.sleep(1)

        logging.info("Health monitor thread exiting cleanly")

    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.connected and self.interface is not None

    def get_health_status(self) -> dict[str, Any]:
        """Get detailed health status for debugging"""
        with self.lock:
            return {
                "connected": self.connected,
                "connection_errors": self.connection_errors,
                "max_connection_errors": self.max_connection_errors,
                "last_heartbeat": self.last_heartbeat,
                "health_monitor_alive": hasattr(self, "health_thread")
                and self.health_thread.is_alive(),
                "stop_event_set": self.stop_event.is_set(),
                "interface_exists": self.interface is not None,
                "connected_node_id": self.connected_node_id,
                "health_check_interval": self.health_check_interval,
                "time_since_last_heartbeat": time.time() - self.last_heartbeat
                if self.last_heartbeat
                else None,
            }

    def is_health_monitor_working(self) -> bool:
        """Check if the health monitor thread is alive and working"""
        return hasattr(self, "health_thread") and self.health_thread.is_alive()

    def force_reconnect(self) -> None:
        """Force immediate reconnection - useful when connection errors are detected externally"""
        logging.warning(
            "Forcing immediate reconnection due to external error detection"
        )
        with self.lock:
            self.connected = False
            self.connection_errors += 1

        if not self.stop_event.is_set():
            self.reconnect(skip_lock=True)

    def handle_external_error(self, error_msg: str) -> None:
        """Handle external connection errors (like 'Connection refused')"""
        logging.warning(f"Handling external connection error: {error_msg}")
        with self.lock:
            self.connected = False
            self.connection_errors += 1
            logging.info(
                f"Updated connection state: connected=False, errors={self.connection_errors}"
            )

        if not self.stop_event.is_set():
            logging.info("Triggering immediate reconnection due to external error")
            self.reconnect(skip_lock=True)

    def get_interface(self) -> Any | None:
        """Get the current interface, reconnecting if necessary"""
        if not self.is_connected():
            if not self.reconnect():
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
                logging.warning(f"Error closing interface: {e}")
        self.connected = False
