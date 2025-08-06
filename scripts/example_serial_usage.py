#!/usr/bin/env python3
"""
Example script demonstrating serial interface usage in nhmesh-producer.

This script shows how to use the new serial interface support to connect
directly to a Meshtastic device via USB serial connection.
"""

import os
import sys
import subprocess
import time


def print_banner():
    """Print a banner for the example"""
    print("=" * 60)
    print("NHMesh Producer - Serial Interface Example")
    print("=" * 60)
    print()


def print_usage_examples():
    """Print usage examples for serial interface"""
    print("USAGE EXAMPLES:")
    print("-" * 30)

    print("\n1. Basic Serial Connection:")
    print("   python -m nhmesh_producer.producer \\")
    print("     --connection-type serial \\")
    print("     --serial-port /dev/ttyUSB0 \\")
    print("     --broker mqtt.nhmesh.live \\")
    print("     --topic msh/US/NH/")

    print("\n2. Serial Connection with Authentication:")
    print("   python -m nhmesh_producer.producer \\")
    print("     --connection-type serial \\")
    print("     --serial-port /dev/ttyUSB0 \\")
    print("     --broker mqtt.nhmesh.live \\")
    print("     --username your_username \\")
    print("     --password your_password \\")
    print("     --topic msh/US/NH/")

    print("\n3. Serial Connection with MQTT Listener:")
    print("   python -m nhmesh_producer.producer \\")
    print("     --connection-type serial \\")
    print("     --serial-port /dev/ttyUSB0 \\")
    print("     --broker mqtt.nhmesh.live \\")
    print("     --topic msh/US/NH/ \\")
    print("     --mqtt-listen-topic msh/US/NH/send")

    print("\n4. Environment Variables:")
    print("   export CONNECTION_TYPE=serial")
    print("   export SERIAL_PORT=/dev/ttyUSB0")
    print("   export MQTT_ENDPOINT=mqtt.nhmesh.live")
    print("   export MQTT_TOPIC=msh/US/NH/")
    print("   python -m nhmesh_producer.producer")

    print("\n5. Docker with Serial:")
    print("   docker run -d \\")
    print("     --name nhmesh-producer \\")
    print("     --device /dev/ttyUSB0:/dev/ttyUSB0 \\")
    print("     -e CONNECTION_TYPE=serial \\")
    print("     -e SERIAL_PORT=/dev/ttyUSB0 \\")
    print("     -e MQTT_ENDPOINT=mqtt.nhmesh.live \\")
    print("     -e MQTT_TOPIC=msh/US/NH/ \\")
    print("     ghcr.io/nhmesh/producer:latest")


def print_serial_port_info():
    """Print information about finding serial ports"""
    print("\nFINDING YOUR SERIAL PORT:")
    print("-" * 30)

    print("\nLinux:")
    print("  ls /dev/tty*")
    print("  lsusb")
    print("  dmesg | grep tty")

    print("\nmacOS:")
    print("  ls /dev/tty.*")
    print("  system_profiler SPUSBDataType")

    print("\nWindows:")
    print("  mode")
    print("  (Check Device Manager for COM ports)")


def print_troubleshooting():
    """Print troubleshooting tips"""
    print("\nTROUBLESHOOTING:")
    print("-" * 30)

    print("\n1. Permission Denied:")
    print("   sudo usermod -a -G dialout $USER")
    print("   # Then log out and back in")

    print("\n2. Port Not Found:")
    print("   - Check if device is connected")
    print("   - Try different port names (ttyUSB0, ttyACM0)")
    print("   - Unplug and reconnect USB cable")

    print("\n3. Connection Timeout:")
    print("   - Ensure device is powered on")
    print("   - Check device is not connected to another app")
    print("   - Restart the Meshtastic device")

    print("\n4. Device Busy:")
    print("   - Close other applications using the port")
    print("   - Check if Meshtastic is running on device")
    print("   - Restart the Meshtastic device")


def test_serial_connection():
    """Test if we can run the producer with serial connection"""
    print("\nTESTING SERIAL CONNECTION:")
    print("-" * 30)

    # Check if we have a serial port to test with
    serial_port = os.getenv("SERIAL_PORT")

    if not serial_port:
        print("⚠️  No SERIAL_PORT environment variable set")
        print("   Set SERIAL_PORT to test serial connection")
        print("   Example: export SERIAL_PORT=/dev/ttyUSB0")
        return False

    print(f"Testing with serial port: {serial_port}")

    # Check if the port exists
    if not os.path.exists(serial_port):
        print(f"❌ Serial port {serial_port} does not exist")
        print("   Check your device connection and port name")
        return False

    print(f"✅ Serial port {serial_port} exists")

    # Try to run the producer with minimal options
    try:
        cmd = [
            sys.executable,
            "-m",
            "nhmesh_producer.producer",
            "--connection-type",
            "serial",
            "--serial-port",
            serial_port,
            "--broker",
            "test",
            "--username",
            "test",
            "--password",
            "test",
            "--mqtt-listen-topic",
            "test",
        ]

        print("Testing producer startup...")
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode == 0:
            print("✅ Producer started successfully")
            return True
        else:
            print(f"❌ Producer failed to start: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("✅ Producer started (timed out as expected)")
        return True
    except Exception as e:
        print(f"❌ Error testing producer: {e}")
        return False


def main():
    """Main function"""
    print_banner()

    print("This example demonstrates how to use the new serial interface")
    print("support in nhmesh-producer to connect directly to Meshtastic")
    print("devices via USB serial connection.")
    print()

    print_usage_examples()
    print_serial_port_info()
    print_troubleshooting()

    # Test serial connection if possible
    test_serial_connection()

    print("\n" + "=" * 60)
    print("For more information, see docs/serial_interface_support.md")
    print("=" * 60)


if __name__ == "__main__":
    main()
