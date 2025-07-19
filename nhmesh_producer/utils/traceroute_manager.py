import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import TYPE_CHECKING, Any, Literal

from utils.deduplicated_queue import DeduplicatedQueue

if TYPE_CHECKING:
    from utils.connection_manager import ConnectionManager
    from utils.node_cache import NodeCache

# Type alias for traceroute result
TracerouteResult = Literal["success", "connection_error", "failure"]


class TracerouteManager:
    """
    Manages traceroute operations with exponential backoff and retry logic.

    Configuration via environment variables:
    - TRACEROUTE_COOLDOWN: Minimum time between any traceroute operations in seconds (default: 180 = 3 minutes)
    - TRACEROUTE_INTERVAL: Interval between periodic traceroutes in seconds (default: 43200 = 12 hours)
    - TRACEROUTE_MAX_RETRIES: Maximum number of retry attempts for failed traceroutes (default: 3)
    - TRACEROUTE_MAX_BACKOFF: Maximum backoff time in seconds (default: 86400 = 24 hours)
    - TRACEROUTE_SEND_TIMEOUT: Timeout for individual traceroute send operations in seconds (default: 30)
    - TRACEROUTE_MAX_THREADS: Maximum number of concurrent traceroute threads (default: 2)
    - TRACEROUTE_PERSISTENCE_FILE: Path to file for persisting retry/backoff state (default: /tmp/traceroute_state.json)
    """

    def __init__(
        self,
        node_cache: "NodeCache",
        connection_manager: "ConnectionManager",
        traceroute_cooldown: int | None = None,
        traceroute_interval: int | None = None,
        max_retries: int | None = None,
        max_backoff: int | None = None,
        traceroute_persistence_file: str = "/tmp/traceroute_state.json",
    ) -> None:
        """
        Initialize the TracerouteManager.

        Args:
            node_cache: The NodeCache instance for node information lookup
            connection_manager: ConnectionManager for interface access and connection health
            traceroute_cooldown (int): Minimum time between any traceroute operations in seconds (default from env or 180)
            traceroute_interval (int): Interval between periodic traceroutes in seconds (default from env or 43200)
            max_retries (int): Maximum number of retry attempts (default from env or 3)
            max_backoff (int): Maximum backoff time in seconds (default from env or 86400)
            persistence_file (str): Path to file for persisting retry/backoff data (default from env or '/tmp/traceroute_state.json')
        """
        self.node_cache = node_cache
        self.connection_manager = connection_manager

        # Configuration with environment variable defaults or passed parameters
        self._TRACEROUTE_INTERVAL: int = (
            traceroute_interval
            if traceroute_interval is not None
            else int(os.getenv("TRACEROUTE_INTERVAL", 12 * 60 * 60))
        )  # Default: 12 hours
        self._TRACEROUTE_COOLDOWN: int = (
            traceroute_cooldown
            if traceroute_cooldown is not None
            else int(os.getenv("TRACEROUTE_COOLDOWN", 3 * 60))
        )  # Default: 3 minutes
        self._last_global_traceroute_time: float = 0  # Global cooldown timestamp
        self._MAX_RETRIES: int = (
            max_retries
            if max_retries is not None
            else int(os.getenv("TRACEROUTE_MAX_RETRIES", 3))
        )  # Default: 3 retries
        self._MAX_BACKOFF: int = (
            max_backoff
            if max_backoff is not None
            else int(os.getenv("TRACEROUTE_MAX_BACKOFF", 24 * 60 * 60))
        )  # Default: 24 hours

        # Persistence configuration
        self._persistence_file = traceroute_persistence_file
        self._persistence_lock = threading.Lock()  # Thread-safe file operations

        # Traceroute tracking (initialized from persistence or empty)
        self._last_traceroute_time: dict[
            str, float
        ] = {}  # node_id -> timestamp when last traceroute was sent
        self._node_failure_counts: dict[
            str, int
        ] = {}  # node_id -> count of consecutive failures
        self._node_backoff_until: dict[
            str, float
        ] = {}  # node_id -> timestamp when node can be retried again

        # Load persisted state
        self._load_state()

        # Queue and threading
        self._traceroute_queue: DeduplicatedQueue[tuple[str, int]] = DeduplicatedQueue(
            key_func=lambda x: x[0]
        )
        self._shutdown_flag = threading.Event()  # Flag to signal shutdown

        # Thread pool for non-blocking traceroute execution with limited concurrency
        max_traceroute_threads = int(os.getenv("TRACEROUTE_MAX_THREADS", 2))
        self._traceroute_executor = ThreadPoolExecutor(
            max_workers=max_traceroute_threads, thread_name_prefix="TracerouteExec"
        )

        # Start worker thread
        self._traceroute_worker_thread = threading.Thread(
            target=self._traceroute_worker, daemon=True
        )
        self._traceroute_worker_thread.start()
        logging.info(
            f"Traceroute worker thread started with single-threaded processing and {self._TRACEROUTE_COOLDOWN}s cooldown."
        )
        logging.info(
            f"Traceroute configuration: interval={self._TRACEROUTE_INTERVAL}s, max_retries={self._MAX_RETRIES}, max_backoff={self._MAX_BACKOFF}s, max_threads={max_traceroute_threads}"
        )
        logging.info(f"Traceroute persistence: {self._persistence_file}")

    def _load_state(self) -> None:
        """
        Load persisted traceroute state from filesystem.
        """
        try:
            if os.path.exists(self._persistence_file):
                with open(self._persistence_file) as f:
                    data = json.load(f)

                # Load data with validation
                self._last_traceroute_time = data.get("last_traceroute_time", {})
                self._node_failure_counts = data.get("node_failure_counts", {})
                self._node_backoff_until = data.get("node_backoff_until", {})

                # Clean up expired backoffs
                now = time.time()
                expired_nodes: list[str] = []
                for node_id, backoff_until in self._node_backoff_until.items():
                    if backoff_until < now:
                        expired_nodes.append(node_id)
                        time_expired = now - backoff_until
                        logging.info(
                            f"[Persistence] Node {node_id} backoff expired {time_expired / 60:.1f} minutes ago, cleaning up"
                        )

                for node_id in expired_nodes:
                    del self._node_backoff_until[node_id]
                    # Also clear failure counts for expired backoffs
                    if node_id in self._node_failure_counts:
                        failure_count = self._node_failure_counts[node_id]
                        logging.info(
                            f"[Persistence] Clearing {failure_count} failure count(s) for expired node {node_id}"
                        )
                        del self._node_failure_counts[node_id]

                # Log detailed state information
                total_nodes_with_state = len(
                    set(self._last_traceroute_time.keys())
                    | set(self._node_failure_counts.keys())
                    | set(self._node_backoff_until.keys())
                )

                logging.info(
                    f"[Persistence] Loaded state for {total_nodes_with_state} nodes total:"
                )
                logging.info(
                    f"[Persistence] - {len(self._last_traceroute_time)} nodes with traceroute history"
                )
                logging.info(
                    f"[Persistence] - {len(self._node_failure_counts)} nodes with active failures"
                )
                logging.info(
                    f"[Persistence] - {len(self._node_backoff_until)} nodes in backoff"
                )

                if expired_nodes:
                    logging.info(
                        f"[Persistence] Cleaned up {len(expired_nodes)} expired backoffs: {', '.join(expired_nodes)}"
                    )

                # Log nodes with active failures and backoffs for debugging
                if self._node_failure_counts:
                    failure_details: list[str] = [
                        f"{node_id}({count})"
                        for node_id, count in self._node_failure_counts.items()
                    ]
                    logging.info(
                        f"[Persistence] Nodes with active failures: {', '.join(failure_details)}"
                    )

                if self._node_backoff_until:
                    backoff_details: list[str] = []
                    for node_id, backoff_until in self._node_backoff_until.items():
                        remaining_time = (backoff_until - now) / 60
                        backoff_details.append(f"{node_id}({remaining_time:.1f}m)")
                    logging.info(
                        f"[Persistence] Nodes in backoff: {', '.join(backoff_details)}"
                    )
            else:
                logging.info(
                    f"[Persistence] No existing state file found at {self._persistence_file}, starting fresh"
                )
        except Exception as e:
            logging.error(
                f"[Persistence] Failed to load state from {self._persistence_file}: {e}, starting fresh"
            )
            self._last_traceroute_time = {}
            self._node_failure_counts = {}
            self._node_backoff_until = {}

    def _save_state(self) -> None:
        """
        Save current traceroute state to filesystem.
        """
        try:
            with self._persistence_lock:
                # Prepare data to save
                data = {
                    "last_traceroute_time": self._last_traceroute_time,
                    "node_failure_counts": self._node_failure_counts,
                    "node_backoff_until": self._node_backoff_until,
                    "saved_at": time.time(),
                }

                # Write to temporary file first, then rename (atomic operation)
                temp_file = f"{self._persistence_file}.tmp"
                with open(temp_file, "w") as f:
                    json.dump(data, f, indent=2)

                # Atomic rename
                os.rename(temp_file, self._persistence_file)
                logging.debug(f"[Persistence] State saved to {self._persistence_file}")
        except Exception as e:
            logging.error(
                f"[Persistence] Failed to save state to {self._persistence_file}: {e}"
            )

    def cleanup(self) -> None:
        """
        Cleanup resources and save final state.
        """
        logging.info("[TracerouteManager] Cleaning up and saving final state...")

        # Signal shutdown to worker thread
        self._shutdown_flag.set()
        logging.info("[TracerouteManager] Shutdown flag set")

        # Shutdown the thread pool without waiting
        if hasattr(self, "_traceroute_executor"):
            logging.info("[TracerouteManager] Shutting down traceroute thread pool...")

            # First try graceful shutdown
            self._traceroute_executor.shutdown(wait=False)

            # Then try to force shutdown any remaining threads
            try:
                # Access the internal thread pool to force shutdown
                if hasattr(self._traceroute_executor, "_threads"):
                    for thread in self._traceroute_executor._threads:
                        if thread.is_alive():
                            logging.warning(
                                f"[TracerouteManager] Force-stopping thread {thread.name}"
                            )
                            # Note: Python doesn't have thread.stop(), but we can try other approaches
            except Exception as e:
                logging.debug(f"[TracerouteManager] Error during force shutdown: {e}")

            logging.info(
                "[TracerouteManager] Traceroute thread pool shutdown initiated."
            )

        # Wait for worker thread to finish (with shorter timeout)
        if (
            hasattr(self, "_traceroute_worker_thread")
            and self._traceroute_worker_thread.is_alive()
        ):
            logging.info("[TracerouteManager] Waiting for worker thread to finish...")
            self._traceroute_worker_thread.join(timeout=0.5)  # Very short timeout
            if self._traceroute_worker_thread.is_alive():
                logging.warning(
                    "[TracerouteManager] Worker thread did not finish cleanly within 0.5 seconds - likely stuck in traceroute execution"
                )
            else:
                logging.info("[TracerouteManager] Worker thread finished cleanly")

        self._save_state()

    def _calculate_backoff_time(self, failure_count: int) -> int:
        """
        Calculate exponential backoff time based on failure count.
        Uses the traceroute interval as the base backoff time.

        Args:
            failure_count (int): Number of consecutive failures

        Returns:
            int: Backoff time in seconds
        """
        if failure_count < 2:
            return 0  # No backoff for first failure

        # Exponential backoff: traceroute_interval * 2^(failures-2)
        backoff_multiplier = 2 ** (failure_count - 2)
        backoff_time = min(
            self._TRACEROUTE_INTERVAL * backoff_multiplier, self._MAX_BACKOFF
        )
        return backoff_time

    def _is_node_in_backoff(self, node_id: str) -> bool:
        """
        Check if a node is currently in backoff period.

        Args:
            node_id (str): The node ID to check

        Returns:
            bool: True if node is in backoff, False otherwise
        """
        if node_id not in self._node_backoff_until:
            return False

        now = time.time()
        return now < self._node_backoff_until[node_id]

    def record_traceroute_success(self, node_id: str) -> None:
        """
        Record a successful traceroute for a node, resetting failure count.

        Args:
            node_id (str): The node ID that succeeded
        """
        node_id = str(node_id)

        self._last_traceroute_time[node_id] = time.time()

        if node_id in self._node_failure_counts:
            failure_count = self._node_failure_counts[node_id]
            logging.info(
                f"[Traceroute] Node {node_id} traceroute succeeded after {failure_count} failures, resetting backoff."
            )
            del self._node_failure_counts[node_id]
        else:
            # Log success for nodes without previous failures
            logging.info(f"[Traceroute] Node {node_id} traceroute succeeded.")

        if node_id in self._node_backoff_until:
            del self._node_backoff_until[node_id]

        self._save_state()

    def _record_traceroute_failure(self, node_id: str) -> bool:
        """
        Record a failed traceroute for a node and calculate backoff.

        Args:
            node_id (str): The node ID that failed

        Returns:
            bool: True if node should be retried, False if max retries exceeded
        """
        node_id = str(node_id)
        failure_count = self._node_failure_counts.get(node_id, 0) + 1
        self._node_failure_counts[node_id] = failure_count

        if failure_count >= self._MAX_RETRIES:
            logging.warning(
                f"[Traceroute] Node {node_id} has failed {failure_count} times, giving up."
            )
            # Save state after updating failure count
            self._save_state()
            return False

        backoff_time = self._calculate_backoff_time(failure_count)
        if backoff_time > 0:
            self._node_backoff_until[node_id] = time.time() + backoff_time
            logging.info(
                f"[Traceroute] Node {node_id} failed {failure_count} times, backing off for {backoff_time / 60:.1f} minutes."
            )
        else:
            logging.info(
                f"[Traceroute] Node {node_id} failed {failure_count} times, no backoff applied yet."
            )

        # Save state after updating failure and backoff data
        self._save_state()
        return True

    def _format_position(self, pos: tuple[float, float, float | None] | None) -> str:
        """
        Format position tuple for display.

        Args:
            pos: Tuple of (lat, lon, alt) or None

        Returns:
            str: Formatted position string
        """
        if pos is None:
            return "UNKNOWN"
        lat, lon, alt = pos
        s = f"({lat:.7f}, {lon:.7f})"
        if alt is not None:
            s += f" {alt}m"
        return s

    def _run_traceroute(self, node_id: str) -> TracerouteResult:
        """
        Execute a traceroute for the given node.

        Args:
            node_id (str): The node ID to traceroute

        Returns:
            TracerouteResult:
                - "success" if successful
                - "connection_error" for interface issues
                - "failure" for actual traceroute failures
        """
        # Early exit if shutdown is requested
        if self._shutdown_flag.is_set():
            logging.info(
                f"[Traceroute] Shutdown requested, skipping traceroute for {node_id}"
            )
            return "connection_error"

        node_id = str(node_id)  # Ensure node_id is always a string
        entry = self.node_cache.get_node_info(node_id)
        long_name = entry.get("long_name")
        pos = entry.get("position")
        failure_count = self._node_failure_counts.get(node_id, 0)

        logging.info(
            f"[Traceroute] Running traceroute for Node {node_id} | Long name: {long_name if long_name else 'UNKNOWN'} | Position: {self._format_position(pos)} | Failures: {failure_count}"
        )

        # Get interface from connection manager
        interface = self.connection_manager.get_ready_interface()
        if interface is None:
            logging.info(
                f"[Traceroute] No interface available for traceroute to node {node_id}, will retry when connection is restored"
            )
            return "connection_error"

        # Update global traceroute time
        self._last_global_traceroute_time = time.time()
        logging.debug(
            f"[Traceroute] About to send traceroute to {node_id} and setting last traceroute time."
        )

        # Execute the traceroute
        return self._execute_traceroute(interface, node_id)

    def _execute_traceroute(self, interface: Any, node_id: str) -> TracerouteResult:
        """Execute the actual traceroute command."""
        timeout_seconds = (
            2
            if self._shutdown_flag.is_set()
            else int(os.getenv("TRACEROUTE_SEND_TIMEOUT", 30))
        )
        future = None

        try:
            # Submit traceroute to thread pool
            future = self._traceroute_executor.submit(
                interface.sendTraceRoute,
                dest=node_id.replace("!", ""),  # Remove '!' prefix if present
                hopLimit=7,
            )

            # Wait for completion
            future.result(timeout=timeout_seconds)
            logging.info(f"[Traceroute] Traceroute command sent for node {node_id}.")
            return "success"

        except FutureTimeoutError:
            logging.error(
                f"[Traceroute] Traceroute to node {node_id} timed out after {timeout_seconds} seconds"
            )
            if future:
                future.cancel()
            self._record_traceroute_failure(node_id)
            return "failure"
        except Exception as e:
            logging.info(
                f"[Traceroute] Interface error during traceroute for node {node_id}: {e}"
            )
            return "connection_error"

    def _traceroute_worker(self) -> None:
        """
        Worker thread that processes traceroute jobs from the queue.
        """
        while not self._shutdown_flag.is_set():
            try:
                # Get the next job from the queue with timeout to check shutdown flag
                try:
                    node_id, retries = self._traceroute_queue.get(timeout=1.0)
                except Exception:
                    # Timeout or empty queue, check shutdown flag and continue
                    continue

                logging.info(
                    f"[Traceroute] Worker picked up job for node {node_id}, attempt {retries + 1}."
                )
                logging.info(
                    f"[Traceroute] Current queue depth: {self._traceroute_queue.qsize()}"
                )

                # Check shutdown flag before processing
                if self._shutdown_flag.is_set():
                    logging.info(
                        "[Traceroute] Worker thread received shutdown signal, exiting"
                    )
                    break

                # Check if this node is in backoff period
                if self._is_node_in_backoff(node_id):
                    backoff_remaining = self._node_backoff_until[node_id] - time.time()
                    logging.info(
                        f"[Traceroute] Node {node_id} is in backoff for {backoff_remaining / 60:.1f} more minutes, re-queueing for later."
                    )

                    # Re-queue the job for later processing if not shutting down
                    if not self._shutdown_flag.is_set():
                        self._traceroute_queue.put((node_id, retries))

                    # Add a small delay to prevent busy loop when all nodes are in backoff
                    self._shutdown_flag.wait(timeout=5.0)  # Interruptible sleep
                    continue

                # Check global cooldown before processing
                now = time.time()
                time_since_last = now - self._last_global_traceroute_time

                if time_since_last < self._TRACEROUTE_COOLDOWN:
                    wait_time = self._TRACEROUTE_COOLDOWN - time_since_last
                    logging.info(
                        f"[Traceroute] Global cooldown active, sleeping {wait_time:.1f} seconds before processing node {node_id}"
                    )

                    # Sleep in small increments to remain responsive to shutdown signal
                    while wait_time > 0 and not self._shutdown_flag.is_set():
                        sleep_duration = min(
                            wait_time, 1.0
                        )  # Sleep max 1 second at a time
                        self._shutdown_flag.wait(
                            timeout=sleep_duration
                        )  # Interruptible sleep
                        wait_time -= sleep_duration

                        # Re-check if we still need to wait (in case another traceroute completed)
                        current_time = time.time()
                        remaining_cooldown = self._TRACEROUTE_COOLDOWN - (
                            current_time - self._last_global_traceroute_time
                        )
                        if remaining_cooldown <= 0:
                            break
                        wait_time = min(wait_time, remaining_cooldown)

                    # Check shutdown flag after waiting
                    if self._shutdown_flag.is_set():
                        logging.info(
                            "[Traceroute] Worker thread received shutdown signal during cooldown, exiting"
                        )
                        break

                result = self._run_traceroute(node_id)
                failure_count = self._node_failure_counts.get(node_id, 0)

                if result == "success":
                    logging.info(
                        f"[Traceroute] Traceroute for node {node_id} completed successfully."
                    )
                elif result == "connection_error":
                    logging.info(
                        f"[Traceroute] Connection issue for node {node_id}, re-queueing without counting as failure"
                    )
                    # Re-queue immediately without incrementing retry count - this is a connection issue
                    if not self._shutdown_flag.is_set():
                        self._traceroute_queue.put((node_id, retries))
                elif result == "failure":
                    logging.info(
                        f"[Traceroute] Traceroute failed for node {node_id} after {retries + 1} attempts. Total failures: {failure_count}"
                    )

                    # Check if we should retry this node (based on failure count and max retries)
                    if (
                        failure_count < self._MAX_RETRIES
                        and not self._shutdown_flag.is_set()
                    ):
                        # Re-queue with incremented retry count if we haven't hit max retries
                        new_retries = retries + 1
                        logging.info(
                            f"[Traceroute] Re-queueing node {node_id} for retry {new_retries + 1}/{self._MAX_RETRIES}"
                        )
                        self._traceroute_queue.put((node_id, new_retries))
                    else:
                        if self._shutdown_flag.is_set():
                            logging.info(
                                f"[Traceroute] Shutdown signal received, not re-queueing node {node_id}"
                            )
                        else:
                            logging.info(
                                f"[Traceroute] Node {node_id} has reached maximum retry limit ({self._MAX_RETRIES}), giving up."
                            )

            except Exception as e:
                logging.error(f"[Traceroute] Worker encountered error: {e}")

        logging.info("[Traceroute] Worker thread exiting cleanly")

    def process_packet_for_traceroutes(self, node_id: str, is_new_node: bool) -> None:
        """
        Process a node from a packet for traceroute queueing logic.
        This method only handles traceroute-specific logic.

        Args:
            node_id (str): The node ID from the packet
            is_new_node (bool): Whether this is a new node (from NodeCache)
        """
        node_id = str(node_id)  # Ensure node_id is always a string

        # Enqueue traceroute for new nodes
        if is_new_node:
            if self._is_node_in_backoff(node_id):
                backoff_remaining = self._node_backoff_until[node_id] - time.time()
                logging.debug(
                    f"[Traceroute] New node {node_id} is in backoff for {backoff_remaining / 60:.1f} more minutes, skipping."
                )
            elif self._traceroute_queue.put((node_id, 0)):  # 0 retries so far
                logging.info(
                    f"[Traceroute] New node discovered: {node_id}, enqueued traceroute job."
                )
            else:
                logging.debug(
                    f"[Traceroute] New node {node_id} already queued, skipping duplicate."
                )

        # Periodic re-traceroute
        now = time.time()
        last_time = self._last_traceroute_time.get(node_id, 0)
        if now - last_time > self._TRACEROUTE_INTERVAL:
            if self._is_node_in_backoff(node_id):
                backoff_remaining = self._node_backoff_until[node_id] - time.time()
                logging.debug(
                    f"[Traceroute] Periodic traceroute for node {node_id} is in backoff for {backoff_remaining / 60:.1f} more minutes, skipping."
                )
            elif self._traceroute_queue.put((node_id, 0)):  # 0 retries so far
                logging.info(
                    f"[Traceroute] Periodic traceroute needed for node {node_id}, enqueued job."
                )
            else:
                logging.debug(
                    f"[Traceroute] Periodic traceroute for node {node_id} already queued, skipping duplicate."
                )

    def queue_traceroute(self, node_id: str) -> bool:
        """
        Manually queue a traceroute for a specific node.

        Args:
            node_id (str): The node ID to queue for traceroute

        Returns:
            bool: True if queued successfully, False if already queued or in backoff
        """
        node_id = str(node_id)

        if self._is_node_in_backoff(node_id):
            backoff_remaining = self._node_backoff_until[node_id] - time.time()
            logging.debug(
                f"[Traceroute] Manual traceroute for node {node_id} is in backoff for {backoff_remaining / 60:.1f} more minutes, skipping."
            )
            return False

        if self._traceroute_queue.put((node_id, 0)):  # 0 retries so far
            logging.info(f"[Traceroute] Manual traceroute queued for node {node_id}.")
            return True
        else:
            logging.debug(
                f"[Traceroute] Manual traceroute for node {node_id} already queued, skipping duplicate."
            )
            return False
