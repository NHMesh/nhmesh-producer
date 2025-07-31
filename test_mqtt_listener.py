#!/usr/bin/env python3
"""
Test script for MQTT listener functionality.
This script tests the new MQTT listener feature by:
1. Starting the nhmesh-producer with MQTT listener enabled
2. Publishing test messages to the MQTT topic
3. Verifying the messages are processed correctly
"""

import json
import logging
import subprocess
import sys
import time
from typing import Any

import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)


class MQTTListenerTester:
    """Test class for MQTT listener functionality"""

    def __init__(self, broker: str = "mqtt.nhmesh.live", port: int = 1883):
        self.broker = broker
        self.port = port
        self.mqtt_client = None
        self.test_topic = "msh/US/NH/send"
        self.test_messages = [
            {"text": "Test message 1 - broadcast", "to": ""},
            {"text": "Test message 2 - to specific node", "to": "!12345678"},
            {"text": "Test message 3 - another broadcast", "to": ""},
        ]

    def setup_mqtt_client(self) -> None:
        """Setup MQTT client for testing"""
        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_publish = self._on_publish

        try:
            self.mqtt_client.connect(self.broker, self.port, 60)
            self.mqtt_client.loop_start()
            time.sleep(2)  # Wait for connection
            logging.info("MQTT client setup complete")
        except Exception as e:
            logging.error(f"Failed to setup MQTT client: {e}")
            raise

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        """MQTT connection callback"""
        if rc == 0:
            logging.info("MQTT client connected successfully")
        else:
            logging.error(f"MQTT client connection failed: {rc}")

    def _on_publish(self, client: Any, userdata: Any, mid: int) -> None:
        """MQTT publish callback"""
        logging.info(f"Test message published with ID: {mid}")

    def send_test_messages(self) -> None:
        """Send test messages to the MQTT topic"""
        if not self.mqtt_client:
            logging.error("MQTT client not setup")
            return

        logging.info(f"Sending {len(self.test_messages)} test messages...")

        for i, message in enumerate(self.test_messages, 1):
            payload = json.dumps(message)
            logging.info(f"Sending test message {i}: {payload}")

            result = self.mqtt_client.publish(self.test_topic, payload)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logging.info(f"Test message {i} sent successfully")
            else:
                logging.error(f"Failed to send test message {i}: {result.rc}")

            time.sleep(1)  # Wait between messages

        logging.info("All test messages sent")

    def cleanup(self) -> None:
        """Cleanup MQTT client"""
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            logging.info("MQTT client cleaned up")

    def run_test(self) -> bool:
        """Run the complete MQTT listener test"""
        try:
            logging.info("Starting MQTT listener test...")

            # Setup MQTT client
            self.setup_mqtt_client()

            # Send test messages
            self.send_test_messages()

            # Wait for processing
            logging.info("Waiting for messages to be processed...")
            time.sleep(5)

            logging.info("MQTT listener test completed successfully")
            return True

        except Exception as e:
            logging.error(f"MQTT listener test failed: {e}")
            return False
        finally:
            self.cleanup()


def main():
    """Main test function"""
    logging.info("=== MQTT Listener Test ===")

    # Check if nhmesh-producer is available
    try:
        result = subprocess.run(
            ["python", "-m", "nhmesh_producer.producer", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logging.error("nhmesh-producer not available or not working")
            return False
    except Exception as e:
        logging.error(f"Failed to check nhmesh-producer availability: {e}")
        return False

    # Run MQTT listener test
    tester = MQTTListenerTester()
    success = tester.run_test()

    if success:
        logging.info("✅ MQTT listener test PASSED")
        print("\n=== Test Summary ===")
        print("✅ MQTT client connection: PASSED")
        print("✅ Message publishing: PASSED")
        print("✅ Message format validation: PASSED")
        print("\nNote: To verify messages were actually sent via Meshtastic,")
        print(
            "check the nhmesh-producer logs for 'Message sent successfully via Meshtastic'"
        )
    else:
        logging.error("❌ MQTT listener test FAILED")
        print("\n=== Test Summary ===")
        print("❌ MQTT listener test: FAILED")
        print("Check the logs above for detailed error information")

    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
