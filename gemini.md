# NH Mesh Producer

## Overview
A standalone, resilient MQTT producer for Meshtastic. It acts as a bridge, connecting to a physical node (via TCP or Serial) and publishing its packets to an MQTT broker.

## Tech Stack
- **Language**: Python 3.13+
- **Manager**: Poetry
- **Protocol**: MQTT, Meshtastic Device API

## Key Features
- **Resiliance**: Auto-reconnect logic, exponential backoff.
- **Dual Mode**: Supports both TCP and Serial connections to the node.
- **Traceroute Daemon**: Can automate traceroutes for network mapping.

## Context for Gemini
- This component is the "Edge" of the infrastructure, talking to the radio hardware.
- It was likely extracted from a larger monolith to ensure stability.
- Critical for getting data *out* of the air and *into* the broker.
