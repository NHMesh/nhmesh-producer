"""
ConnectionManager for managing Meshtastic interface connections with automatic reconnection.
"""

import logging
import threading
import time
from typing import Any

import meshtastic
import meshtastic.tcp_interface
import meshtastic.serial_interface


class ConnectionManager:
    """Manages connection health and automatic reconnection for Meshtastic interface"""

    def __init__(
        self,
        node_ip: str | None = None,
        serial_port: str | None = None,
        connection_type: str = "tcp",  # "tcp" or "serial"
        reconnect_attempts: int = 5,
        reconnect_delay: int = 5,
        health_check_interval: int = 10,  # Back to 10 seconds since events handle immediate detection
        packet_timeout: int = 60,  # Reconnect if no packets received for 60 seconds
    ) -> None:
        self.node_ip = node_ip
        self.serial_port = serial_port
        self.connection_type = connection_type.lower()
        self.reconnect_attempts = reconnect_attempts
        self.reconnect_delay = reconnect_delay
        self.health_check_interval = health_check_interval
        self.packet_timeout = packet_timeout
        self.interface: Any = None
        self.connected = False
        self.last_heartbeat = time.time()
        self.last_packet_time = time.time()  # Track when last packet was received
        self.connection_errors = 0
        self.max_connection_errors = 10
        self.lock = threading.RLock()  # Use RLock to allow reentrant locking
        self.stop_event = threading.Event()
        self.node_info: dict[str, Any] | None = None
        self.connected_node_id: str | None = None
        self.last_successful_health_check = time.time()
        self.reconnecting = False  # Flag to prevent multiple simultaneous reconnections
        self.health_check_in_progress = (
            False  # Flag to prevent overlapping health checks
        )
        self.connection_in_progress = (
            False  # Flag to prevent multiple connection attempts
        )
        self.last_connection_time = 0  # Track when we last connected
        self.min_connection_time = 30  # Minimum time between connections (30 seconds)

        # Validate connection parameters
        if self.connection_type == "tcp" and not self.node_ip:
            raise ValueError("node_ip is required for TCP connections")
        elif self.connection_type == "serial" and not self.serial_port:
            raise ValueError("serial_port is required for serial connections")
        elif self.connection_type not in ["tcp", "serial"]:
            raise ValueError("connection_type must be 'tcp' or 'serial'")

        # Start health monitoring thread
        self.health_thread = threading.Thread(target=self._health_monitor, daemon=True)
        self.health_thread.start()

    def packet_received(self) -> None:
        """Call this method when a packet is received to update the last packet time"""
        with self.lock:
            self.last_packet_time = time.time()
            logging.debug(
                f"Packet received, updated last_packet_time to {self.last_packet_time}"
            )

    def _close_interface_safely(self) -> None:
        """Safely close the interface with proper error handling"""
        if self.interface:
            try:
                logging.info("Closing existing interface...")
                # Close the underlying socket first if it exists (for TCP)
                if hasattr(self.interface, "socket") and self.interface.socket:
                    try:
                        logging.debug(f"Closing socket: {self.interface.socket}")
                        self.interface.socket.close()
                        logging.debug("Underlying socket closed")
                    except Exception as e:
                        logging.warning(f"Error closing underlying socket: {e}")

                # Close the interface
                self.interface.close()
                logging.info("Existing interface closed successfully")
            except Exception as e:
                logging.warning(f"Error closing existing interface: {e}")
            finally:
                self.interface = None
                self.connected = False

    def _check_existing_connections(self) -> bool:
        """Check if there are existing connections that should be cleaned up"""
        if self.interface:
            try:
                # For TCP interfaces, check if the interface has a valid socket
                if hasattr(self.interface, "socket") and self.interface.socket:
                    # Try to get socket info to see if it's still valid
                    try:
                        socket_info = self.interface.socket.getsockname()
                        logging.debug(f"Existing socket found: {socket_info}")
                        return True
                    except Exception:
                        logging.warning(
                            "Existing socket appears to be invalid, will be cleaned up"
                        )
                        return False
                else:
                    # For serial interfaces, just check if interface exists
                    logging.debug("Interface exists, will be cleaned up")
                    return False
            except Exception as e:
                logging.warning(f"Error checking existing connections: {e}")
                return False
        return False

    def connect(self, skip_lock: bool = False) -> bool:
        """Establish connection to Meshtastic node with error handling"""
        logging.info(f"connect() called with skip_lock={skip_lock}")

        def _connect_internal() -> bool:
            """Internal connection logic with proper cleanup"""
            # Check if connection is already in progress
            if self.connection_in_progress:
                logging.info("Connection already in progress, skipping")
                return False

            # Check for existing connections
            if self._check_existing_connections():
                logging.info(
                    "Existing connection found, will be cleaned up before new connection"
                )

            self.connection_in_progress = True
            try:
                # Always close existing interface first
                self._close_interface_safely()

                if self.connection_type == "tcp":
                    logging.info(f"Connecting to Meshtastic node at {self.node_ip}")
                    self.interface = meshtastic.tcp_interface.TCPInterface(
                        hostname=self.node_ip
                    )
                    logging.info(f"TCPInterface created successfully: {self.interface}")

                    # Log socket information for debugging
                    if hasattr(self.interface, "socket") and self.interface.socket:
                        logging.debug(f"Socket created: {self.interface.socket}")
                        try:
                            socket_info = self.interface.socket.getsockname()
                            logging.debug(f"Socket local address: {socket_info}")
                        except Exception as e:
                            logging.debug(f"Could not get socket info: {e}")

                elif self.connection_type == "serial":
                    logging.info(f"Connecting to Meshtastic node via serial at {self.serial_port}")
                    self.interface = meshtastic.serial_interface.SerialInterface(
                        self.serial_port, debugOut=False
                    )
                    logging.info(f"SerialInterface created successfully: {self.interface}")

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
                self.last_successful_health_check = time.time()
                self.last_connection_time = (
                    time.time()
                )  # Update last connection time on successful connection

                logging.info(f"Successfully connected to node {self.connected_node_id}")
                return True

            except Exception as e:
                error_str = str(e).lower()
                if any(
                    keyword in error_str
                    for keyword in [
                        "broken pipe",
                        "connection reset",
                        "connection refused",
                        "serial",
                        "timeout",
                    ]
                ):
                    logging.warning(
                        f"Connection error detected (likely remote server issue): {e}"
                    )
                    # For these specific errors, don't increment connection_errors as aggressively
                    # since they're likely server-side issues
                    if (
                        self.connection_errors < 5
                    ):  # Only increment if we haven't had too many errors
                        self.connection_errors += 1
                else:
                    logging.error(f"Failed to connect to Meshtastic node: {e}")
                    self.connection_errors += 1

                self.connected = False
                # Clean up failed interface
                self._close_interface_safely()
                return False
            finally:
                self.connection_in_progress = False

        if skip_lock:
            # Health monitor thread - use existing lock to prevent race conditions
            with self.lock:
                return _connect_internal()
        else:
            # Main thread - use lock
            with self.lock:
                return _connect_internal()

    def reconnect(self, skip_lock: bool = False) -> bool:
        """Attempt to reconnect with exponential backoff and proper synchronization"""
        logging.info(f"reconnect() called with skip_lock={skip_lock}")

        def _reconnect_internal() -> bool:
            """Internal reconnection logic with proper state management"""
            # Check if already reconnecting to prevent multiple simultaneous reconnections
            if self.reconnecting:
                logging.info("Reconnection already in progress, skipping")
                return False

            self.reconnecting = True
            try:
                attempts = 0
                while (
                    attempts < self.reconnect_attempts and not self.stop_event.is_set()
                ):
                    attempts += 1
                    logging.info(
                        f"Reconnection attempt {attempts}/{self.reconnect_attempts}"
                    )

                    logging.info("Calling connect() from reconnect()...")
                    if self.connect(
                        skip_lock=True
                    ):  # Always use skip_lock=True for internal calls
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
                        logging.info(
                            "Shutdown requested during reconnection delay, aborting"
                        )
                        break

                if self.stop_event.is_set():
                    logging.info("Reconnection aborted due to shutdown")
                else:
                    logging.error("Max reconnection attempts reached")
                return False
            finally:
                self.reconnecting = False

        if skip_lock:
            # Health monitor thread - use existing lock
            with self.lock:
                return _reconnect_internal()
        else:
            # Main thread - use lock
            with self.lock:
                return _reconnect_internal()

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

                logging.debug("=== HEALTH MONITOR CYCLE START ===")

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
                    time_since_last_packet = time.time() - self.last_packet_time
                    time_since_last_connection = time.time() - self.last_connection_time

                    # Only attempt reconnection if we have been connected for at least min_connection_time
                    if (
                        self.connected
                        and time_since_last_connection < self.min_connection_time
                    ):
                        logging.debug(
                            f"Not attempting reconnection due to minimum connection time ({time_since_last_connection:.1f}s < {self.min_connection_time}s)"
                        )
                        should_reconnect = False
                    elif (
                        not self.connected
                        or self.connection_errors >= self.max_connection_errors
                        or time_since_last_success
                        > 30  # Force reconnect if no successful check in 30 seconds
                        or time_since_last_packet > self.packet_timeout
                    ):
                        should_reconnect = True

                logging.debug(
                    f"Health check status: connected={current_connected}, errors={current_errors}/{current_max_errors}, interface_exists={interface_exists}, should_reconnect={should_reconnect}, time_since_last_success={time_since_last_success:.1f}s, time_since_last_packet={time_since_last_packet:.1f}s, time_since_last_connection={time_since_last_connection:.1f}s"
                )

                if should_reconnect:
                    if time_since_last_success > 30:
                        logging.warning(
                            f"Connection health check failed - no successful check in {time_since_last_success:.1f}s, forcing reconnection"
                        )
                    elif time_since_last_packet > self.packet_timeout:
                        logging.warning(
                            f"Connection health check failed - no packets received in {time_since_last_packet:.1f}s, forcing reconnection"
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
                    logging.debug("Interface exists, performing health check...")

                    # Prevent overlapping health checks
                    if self.health_check_in_progress:
                        logging.debug("Health check already in progress, skipping")
                        continue

                    self.health_check_in_progress = True
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
                                logging.debug(
                                    "Health check: calling getMyNodeInfo()..."
                                )
                                node_info = self.interface.getMyNodeInfo()
                                logging.debug(
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
                                        logging.debug("Socket health check passed")
                                    except Exception as socket_e:
                                        logging.warning(
                                            f"Socket health check failed: {socket_e}"
                                        )
                                        raise Exception(
                                            f"Socket connection broken: {socket_e}"
                                        ) from socket_e

                                result.success = True  # noqa: B023
                                logging.debug("Health check: getMyNodeInfo() succeeded")
                            except Exception as e:
                                logging.error(
                                    f"Health check: getMyNodeInfo() failed with exception: {e}"
                                )
                                result.exception = e  # noqa: B023

                        # Run health check in separate thread with timeout
                        health_thread = threading.Thread(
                            target=health_check, daemon=True
                        )
                        logging.debug("Starting health check thread...")
                        health_thread.start()
                        health_thread.join(
                            timeout=5
                        )  # Reduced timeout to 5 seconds for faster detection

                        if health_thread.is_alive():
                            # Thread is still running, timeout occurred
                            logging.warning("Health check timed out after 5 seconds")
                            raise TimeoutError("Health check timed out after 5 seconds")

                        logging.debug(
                            f"Health check result: success={result.success}, exception={result.exception}"
                        )

                        if result.success:
                            # Update last heartbeat and reset errors on success
                            with self.lock:
                                self.last_heartbeat = time.time()
                                self.connection_errors = 0
                                self.connected = True  # Ensure connected state is set
                                self.last_successful_health_check = time.time()  # Update last successful check on successful health check
                            logging.debug(
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
                        error_str = str(e).lower()
                        if any(
                            keyword in error_str
                            for keyword in [
                                "broken pipe",
                                "connection reset",
                                "connection refused",
                            ]
                        ):
                            logging.warning(
                                f"Health check failed with connection error (likely server issue): {e}"
                            )
                            # For connection errors, be less aggressive about incrementing errors
                            with self.lock:
                                self.connected = False
                                if (
                                    self.connection_errors < 5
                                ):  # Only increment if we haven't had too many errors
                                    self.connection_errors += 1
                        else:
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
                    finally:
                        self.health_check_in_progress = False
                elif not self.interface and not self.stop_event.is_set():
                    # No interface exists, try to reconnect
                    logging.warning("No interface exists, attempting reconnection")
                    with self.lock:
                        self.connected = False
                        self.connection_errors += 1

                    if not self.stop_event.is_set():
                        self.reconnect(skip_lock=True)
                else:
                    logging.debug(
                        "Skipping health check - interface doesn't exist or shutdown requested"
                    )

                logging.debug("=== HEALTH MONITOR CYCLE END ===")

            except Exception as e:
                logging.error(f"Error in health monitor: {e}")
                # Don't let exceptions kill the health monitor thread
                time.sleep(1)

        logging.info("Health monitor thread exiting cleanly")

    def is_connected(self) -> bool:
        """Check if currently connected"""
        return self.connected and self.interface is not None

    def get_connection_info(self) -> dict[str, Any]:
        """Get detailed connection information for debugging"""
        with self.lock:
            info = {
                "node_ip": self.node_ip,
                "serial_port": self.serial_port,
                "connection_type": self.connection_type,
                "connected": self.connected,
                "interface_exists": self.interface is not None,
                "connected_node_id": self.connected_node_id,
                "connection_errors": self.connection_errors,
                "reconnecting": self.reconnecting,
                "connection_in_progress": self.connection_in_progress,
                "health_check_in_progress": self.health_check_in_progress,
            }

            if (
                self.interface
                and hasattr(self.interface, "socket")
                and self.interface.socket
            ):
                try:
                    socket = self.interface.socket
                    info["socket_local"] = socket.getsockname()
                    info["socket_remote"] = socket.getpeername()
                    info["socket_fileno"] = socket.fileno()
                except Exception as e:
                    info["socket_error"] = str(e)
            elif self.interface and hasattr(self.interface, "port"):
                info["serial_port"] = self.interface.port

            return info

    def get_health_status(self) -> dict[str, Any]:
        """Get detailed health status for debugging"""
        with self.lock:
            return {
                "connected": self.connected,
                "connection_errors": self.connection_errors,
                "max_connection_errors": self.max_connection_errors,
                "last_heartbeat": self.last_heartbeat,
                "last_packet_time": self.last_packet_time,
                "packet_timeout": self.packet_timeout,
                "health_monitor_alive": hasattr(self, "health_thread")
                and self.health_thread.is_alive(),
                "stop_event_set": self.stop_event.is_set(),
                "interface_exists": self.interface is not None,
                "connected_node_id": self.connected_node_id,
                "health_check_interval": self.health_check_interval,
                "time_since_last_heartbeat": time.time() - self.last_heartbeat
                if self.last_heartbeat
                else None,
                "time_since_last_packet": time.time() - self.last_packet_time
                if self.last_packet_time
                else None,
                "reconnecting": self.reconnecting,
                "health_check_in_progress": self.health_check_in_progress,
                "connection_in_progress": self.connection_in_progress,
                "last_connection_time": self.last_connection_time,
                "min_connection_time": self.min_connection_time,
                "time_since_last_connection": time.time() - self.last_connection_time
                if self.last_connection_time
                else None,
            }

    def is_health_monitor_working(self) -> bool:
        """Check if the health monitor thread is alive and working"""
        return hasattr(self, "health_thread") and self.health_thread.is_alive()

    def is_packet_timeout_expired(self) -> bool:
        """Check if the packet timeout has expired (no packets received for packet_timeout seconds)"""
        with self.lock:
            return time.time() - self.last_packet_time > self.packet_timeout

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

        # Close interface with proper cleanup
        self._close_interface_safely()
