# MQTT Listener Feature

The nhmesh-producer now includes an MQTT listener feature that allows it to receive messages from MQTT topics and send them via the Meshtastic network.

## Overview

This feature enables bidirectional communication:

- **Outbound**: Meshtastic packets are published to MQTT topics (existing functionality)
- **Inbound**: Messages received on MQTT topics are sent via Meshtastic (new functionality)

## Configuration

### Command Line Arguments

Add the `--mqtt-listen-topic` argument to specify which MQTT topic to listen for incoming messages:

```bash
python -m nhmesh_producer.producer \
  --broker mqtt.nhmesh.live \
  --port 1883 \
  --topic msh/US/NH/ \
  --node-ip 192.168.1.100 \
  --mqtt-listen-topic msh/US/NH/send
```

### Environment Variables

You can also set the topic using the `MQTT_LISTEN_TOPIC` environment variable:

```bash
export MQTT_LISTEN_TOPIC="msh/US/NH/send"
python -m nhmesh_producer.producer --broker mqtt.nhmesh.live --node-ip 192.168.1.100
```

## Message Format

Messages sent to the MQTT listen topic should be in JSON format with the following structure:

```json
{
  "text": "Your message content here",
  "to": "!12345678"
}
```

### Fields

- **text** (required): The message content to send via Meshtastic
- **to** (optional): The destination node ID. If empty or omitted, the message will be broadcast to all nodes

### Examples

**Broadcast message:**

```json
{
  "text": "Hello everyone!"
}
```

**Message to specific node:**

```json
{
  "text": "Hello node 12345678!",
  "to": "!12345678"
}
```

## Testing

Use the provided test script to verify the MQTT listener functionality:

```bash
python scripts/test_mqtt_listener.py
```

This script will:

1. Connect to the MQTT broker
2. Send test messages to the configured listen topic
3. Log the results

## Logging

The MQTT listener provides detailed logging:

- Connection status and subscription confirmation
- Received message details
- Message parsing errors
- Meshtastic sending status

Example log output:

```
2024-01-15 10:30:00 - INFO - Connected to MQTT broker
2024-01-15 10:30:00 - INFO - Subscribed to MQTT listen topic: msh/US/NH/send
2024-01-15 10:30:05 - INFO - Received MQTT message on topic 'msh/US/NH/send': {"text": "Hello!", "to": ""}
2024-01-15 10:30:05 - INFO - Sending message via Meshtastic: 'Hello!' to ''
2024-01-15 10:30:05 - INFO - Message sent successfully via Meshtastic
```

## Error Handling

The MQTT listener includes robust error handling:

- **JSON parsing errors**: Invalid JSON messages are logged and ignored
- **Missing text field**: Messages without text content are logged and ignored
- **Connection issues**: Automatic reconnection with the existing connection management system
- **Meshtastic sending errors**: Failed sends are logged with detailed error information

## Security Considerations

- Ensure the MQTT broker is properly secured
- Use authentication if required by your MQTT broker
- Consider message validation and rate limiting for production use
- The listen topic should be carefully chosen to avoid conflicts with other systems

## Integration with Existing Features

The MQTT listener integrates seamlessly with existing features:

- **Connection Management**: Uses the same connection manager for Meshtastic TCP connections
- **Health Monitoring**: Benefits from the existing health monitoring and automatic reconnection
- **Logging**: Uses the same logging configuration as the rest of the application
- **Signal Handling**: Properly handles shutdown signals and cleanup
