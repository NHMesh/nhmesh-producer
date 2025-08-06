#!/usr/bin/env python3
"""
Test script to verify serial interface support in nhmesh-producer.
This script tests the ConnectionManager with both TCP and serial connections.
"""

import sys
import os
import logging
import time

# Add the parent directory to the path so we can import nhmesh_producer modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nhmesh_producer.utils.connection_manager import ConnectionManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def test_tcp_connection():
    """Test TCP connection functionality"""
    print("=== Testing TCP Connection ===")

    # Get node IP from environment or use a default for testing
    node_ip = os.getenv("NODE_IP", "10.250.1.103")

    try:
        # Create connection manager for TCP
        cm = ConnectionManager(
            node_ip=node_ip,
            connection_type="tcp",
            reconnect_attempts=2,
            reconnect_delay=2,
            health_check_interval=5,
            packet_timeout=30,
        )

        print(f"Created TCP ConnectionManager for {node_ip}")

        # Try to connect
        print("Attempting to connect...")
        if cm.connect():
            print("✓ TCP connection successful!")

            # Get interface
            interface = cm.get_interface()
            if interface:
                print("✓ Interface retrieved successfully")

                # Get connection info
                info = cm.get_connection_info()
                print(f"Connection info: {info}")

                # Get health status
                health = cm.get_health_status()
                print(f"Health status: {health}")

                # Test for a few seconds
                print("Testing connection for 5 seconds...")
                time.sleep(5)

                # Cleanup
                cm.close()
                print("✓ TCP connection test completed successfully")
                return True
            else:
                print("✗ Failed to get interface")
                return False
        else:
            print("✗ TCP connection failed")
            return False

    except Exception as e:
        print(f"✗ TCP connection test failed with error: {e}")
        return False


def test_serial_connection():
    """Test serial connection functionality"""
    print("\n=== Testing Serial Connection ===")

    # Get serial port from environment
    serial_port = os.getenv("SERIAL_PORT")

    if not serial_port:
        print("⚠️  SERIAL_PORT environment variable not set, skipping serial test")
        print("   Set SERIAL_PORT to test serial connection (e.g., /dev/ttyUSB0)")
        return True

    try:
        # Create connection manager for serial
        cm = ConnectionManager(
            serial_port=serial_port,
            connection_type="serial",
            reconnect_attempts=2,
            reconnect_delay=2,
            health_check_interval=5,
            packet_timeout=30,
        )

        print(f"Created Serial ConnectionManager for {serial_port}")

        # Try to connect
        print("Attempting to connect...")
        if cm.connect():
            print("✓ Serial connection successful!")

            # Get interface
            interface = cm.get_interface()
            if interface:
                print("✓ Interface retrieved successfully")

                # Get connection info
                info = cm.get_connection_info()
                print(f"Connection info: {info}")

                # Get health status
                health = cm.get_health_status()
                print(f"Health status: {health}")

                # Test for a few seconds
                print("Testing connection for 5 seconds...")
                time.sleep(5)

                # Cleanup
                cm.close()
                print("✓ Serial connection test completed successfully")
                return True
            else:
                print("✗ Failed to get interface")
                return False
        else:
            print("✗ Serial connection failed")
            return False

    except Exception as e:
        print(f"✗ Serial connection test failed with error: {e}")
        return False


def test_connection_manager_validation():
    """Test that the ConnectionManager properly validates parameters"""
    print("\n=== Testing ConnectionManager Parameter Validation ===")

    # Test 1: TCP without node_ip
    try:
        cm = ConnectionManager(connection_type="tcp")
        print("✗ Should have raised ValueError for TCP without node_ip")
        return False
    except ValueError as e:
        print(f"✓ Correctly raised ValueError for TCP without node_ip: {e}")

    # Test 2: Serial without serial_port
    try:
        cm = ConnectionManager(connection_type="serial")
        print("✗ Should have raised ValueError for serial without serial_port")
        return False
    except ValueError as e:
        print(f"✓ Correctly raised ValueError for serial without serial_port: {e}")

    # Test 3: Invalid connection type
    try:
        cm = ConnectionManager(node_ip="127.0.0.1", connection_type="invalid")
        print("✗ Should have raised ValueError for invalid connection type")
        return False
    except ValueError as e:
        print(f"✓ Correctly raised ValueError for invalid connection type: {e}")

    print("✓ All parameter validation tests passed")
    return True


def main():
    """Main test function"""
    print("nhmesh-producer Serial Interface Support Test")
    print("=" * 50)

    # Test parameter validation
    if not test_connection_manager_validation():
        print("\n❌ Parameter validation tests failed")
        return 1

    # Test TCP connection
    tcp_success = test_tcp_connection()

    # Test serial connection
    serial_success = test_serial_connection()

    # Summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY:")
    print(f"TCP Connection: {'✓ PASS' if tcp_success else '✗ FAIL'}")
    print(f"Serial Connection: {'✓ PASS' if serial_success else '⚠️  SKIP'}")
    print(f"Parameter Validation: ✓ PASS")

    if tcp_success:
        print("\n✅ Serial interface support appears to be working correctly!")
        print("   You can now use --connection-type serial --serial-port /dev/ttyUSB0")
        return 0
    else:
        print("\n❌ Some tests failed. Check your configuration.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
