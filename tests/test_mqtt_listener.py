#!/usr/bin/env python3
"""
Test script for the MQTT listener functionality.
This script publishes test messages to the MQTT topic that the nhmesh-producer
is listening on, demonstrating the bidirectional communication.
"""

import json
import logging
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

def on_connect(client: Any, userdata: Any, flags: Any, rc: int) -> None:
    """Callback for MQTT connection"""
    if rc == 0:
        logging.info("Connected to MQTT broker")
    else:
        logging.error(f"Failed to connect to MQTT broker: {rc}")

def on_publish(client: Any, userdata: Any, mid: int) -> None:
    """Callback for MQTT publish"""
    logging.info(f"Message published with ID: {mid}")

def main():
    """Main function to test MQTT listener functionality"""
    
    # Configuration - adjust these values as needed
    broker = "mqtt.nhmesh.live"
    port = 1883
    topic = "msh/US/NH/send"  # Topic to send messages to
    username = None  # Set if authentication is required
    password = None  # Set if authentication is required
    
    # Create MQTT client
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_publish = on_publish
    
    # Set authentication if provided
    if username and password:
        client.username_pw_set(username, password)
    
    try:
        # Connect to MQTT broker
        logging.info(f"Connecting to MQTT broker {broker}:{port}")
        client.connect(broker, port, 60)
        client.loop_start()
        
        # Wait for connection
        time.sleep(2)
        
        # Test messages to send
        test_messages = [
            {
                "text": "Hello from MQTT test script!",
                "to": ""  # Broadcast message
            },
            {
                "text": "This is a test message to a specific node",
                "to": "!12345678"  # Replace with actual node ID
            },
            {
                "text": "Another test message",
                "to": ""  # Broadcast message
            }
        ]
        
        # Send test messages
        for i, message in enumerate(test_messages, 1):
            payload = json.dumps(message)
            logging.info(f"Sending test message {i}: {payload}")
            
            result = client.publish(topic, payload)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logging.info(f"Test message {i} sent successfully")
            else:
                logging.error(f"Failed to send test message {i}: {result.rc}")
            
            # Wait between messages
            time.sleep(2)
        
        # Wait a bit more to ensure messages are processed
        logging.info("Waiting for messages to be processed...")
        time.sleep(5)
        
    except Exception as e:
        logging.error(f"Error during MQTT test: {e}")
    finally:
        # Cleanup
        client.loop_stop()
        client.disconnect()
        logging.info("MQTT test completed")

if __name__ == "__main__":
    main() 