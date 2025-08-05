#!/usr/bin/env python3
"""
Connection monitoring script for nhmesh-producer.
This script helps identify when multiple TCP connections are being created.
"""

import logging
import os
import subprocess
import sys
import time
from typing import Any

# Add the parent directory to the path so we can import nhmesh_producer
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from nhmesh_producer.utils.connection_manager import ConnectionManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


def get_tcp_connections(host: str, port: int = 4403) -> list[dict[str, Any]]:
    """Get current TCP connections to the specified host and port"""
    try:
        # Use netstat to get TCP connections
        result = subprocess.run(
            ["netstat", "-an"], capture_output=True, text=True, timeout=10
        )

        connections = []
        for line in result.stdout.split("\n"):
            if f"{host}:{port}" in line and "ESTABLISHED" in line:
                parts = line.split()
                if len(parts) >= 4:
                    connections.append(
                        {
                            "local": parts[3],
                            "remote": parts[4],
                            "state": parts[5] if len(parts) > 5 else "UNKNOWN",
                        }
                    )

        return connections
    except Exception as e:
        logging.error(f"Error getting TCP connections: {e}")
        return []


def monitor_connections(node_ip: str, interval: int = 5):
    """Monitor connections and connection manager state"""
    logging.info(f"Starting connection monitoring for {node_ip}")
    logging.info(f"Monitoring interval: {interval} seconds")

    # Create a connection manager for testing
    cm = ConnectionManager(node_ip)

    try:
        while True:
            print("\n" + "=" * 80)
            print(f"Connection Monitor - {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("=" * 80)

            # Get TCP connections
            tcp_connections = get_tcp_connections(node_ip)
            print(f"\nTCP Connections to {node_ip}:4403:")
            if tcp_connections:
                for i, conn in enumerate(tcp_connections, 1):
                    print(
                        f"  {i}. {conn['local']} -> {conn['remote']} ({conn['state']})"
                    )
            else:
                print("  No TCP connections found")

            # Get connection manager state
            print("\nConnection Manager State:")
            health_status = cm.get_health_status()
            for key, value in health_status.items():
                print(f"  {key}: {value}")

            # Get detailed connection info
            print("\nDetailed Connection Info:")
            conn_info = cm.get_connection_info()
            for key, value in conn_info.items():
                print(f"  {key}: {value}")

            # Try to connect if not connected
            if not cm.is_connected():
                print("\nAttempting to connect...")
                if cm.connect():
                    print("  Connection successful!")
                else:
                    print("  Connection failed!")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\nMonitoring stopped by user")
    finally:
        cm.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Monitor nhmesh-producer connections")
    parser.add_argument(
        "--node-ip", default="10.250.1.103", help="Node IP address to monitor"
    )
    parser.add_argument(
        "--interval", type=int, default=5, help="Monitoring interval in seconds"
    )

    args = parser.parse_args()

    monitor_connections(args.node_ip, args.interval)
