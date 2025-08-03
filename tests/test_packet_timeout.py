#!/usr/bin/env python3
"""
Test script for packet timeout functionality in ConnectionManager
"""

import logging
import time

from nhmesh_producer.utils.connection_manager import ConnectionManager

# Set up logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s"
)


def test_packet_timeout():
    """Test the packet timeout functionality"""
    print("Testing packet timeout functionality...")

    # Create connection manager with short timeout for testing
    cm = ConnectionManager(
        node_ip="127.0.0.1",  # Dummy IP for testing
        packet_timeout=5,  # 5 second timeout for testing
        health_check_interval=2,  # 2 second health check interval
    )

    try:
        # Test initial state
        print(f"Initial packet timeout expired: {cm.is_packet_timeout_expired()}")

        # Simulate packet received
        print("Simulating packet received...")
        cm.packet_received()

        # Check that timeout is not expired immediately after packet
        print(f"Packet timeout expired after packet: {cm.is_packet_timeout_expired()}")

        # Wait for timeout to expire
        print("Waiting for packet timeout to expire (5 seconds)...")
        time.sleep(6)

        # Check that timeout is now expired
        print(f"Packet timeout expired after wait: {cm.is_packet_timeout_expired()}")

        # Get health status
        status = cm.get_health_status()
        print(f"Health status: {status}")

        print("Packet timeout test completed successfully!")

    finally:
        # Clean up
        cm.close()


if __name__ == "__main__":
    test_packet_timeout()
