# NHMesh Producer

A resilient Meshtastic MQTT producer with automatic reconnection and connection health monitoring. This standalone producer handles the connection to Meshtastic nodes and publishes received packets to an MQTT broker with enhanced error handling and recovery mechanisms.

## Running with Docker

```bash
docker run -d \
    --name nhmesh-producer \
    -e NODE_IP=192.168.1.100 \
    -e MQTT_ENDPOINT=mqtt.nhmesh.live \
    -e MQTT_USERNAME=your_username \
    -e MQTT_PASSWORD=your_password \
    ghcr.io/nhmesh/producer:latest
```

#### Environment Variables

| Variable                       | Default                         | Description                                                    |
| ------------------------------ | ------------------------------- | -------------------------------------------------------------- |
| `LOG_LEVEL`                    | `INFO`                          | Logging level (DEBUG, INFO, WARNING, ERROR)                   |
| `MQTT_ENDPOINT`                | `mqtt.nhmesh.live`              | MQTT broker address                                            |
| `MQTT_PORT`                    | `1883`                          | MQTT broker port                                               |
| `MQTT_USERNAME`                | -                               | MQTT username for authentication                               |
| `MQTT_PASSWORD`                | -                               | MQTT password for authentication                               |
| `NODE_IP`                      | -                               | IP address of the Meshtastic node to connect to               |
| `MQTT_TOPIC`                   | `msh/US/NH/`                    | Root MQTT topic for publishing messages                       |
| `TRACEROUTE_COOLDOWN`          | `180`                           | Minimum time between any traceroute operations in seconds (3 minutes) |
| `TRACEROUTE_INTERVAL`          | `43200`                         | Interval between periodic traceroutes in seconds (12 hours)   |
| `TRACEROUTE_MAX_RETRIES`       | `3`                             | Maximum number of retry attempts for failed traceroutes       |
| `TRACEROUTE_MAX_BACKOFF`       | `86400`                         | Maximum backoff time in seconds for failed nodes (24 hours)   |
| `TRACEROUTE_PERSISTENCE_FILE`  | `/tmp/traceroute_state.json`    | Path to file for persisting retry/backoff state across restarts |

### Command Line Options

```bash
python -m nhmesh_producer.producer \
    --broker mqtt.nhmesh.live \
    --port 1883 \
    --topic msh/US/NH/ \
    --username your_username \
    --password your_password \
    --node-ip 192.168.1.100
```

## Features

### 🔄 **Automatic Reconnection**

- Exponential backoff retry logic for connection failures
- Continuous health monitoring in background thread
- Thread-safe operations with proper locking
- Graceful resource cleanup on shutdown

### 🛡️ **Enhanced Error Handling**

- Specific handling for `BrokenPipeError` and other TCP connection issues
- MQTT connection state management with callbacks
- Packet processing error isolation (errors don't crash the app)
- Safe gateway ID handling with fallback mechanisms

### 📊 **Web Interface**

- Real-time mesh network monitoring dashboard
- Traceroute visualization and analysis
- Network topology mapping
- Packet history and statistics

### 🔍 **Traceroute Daemon**

- Automatic traceroute to new nodes
- Periodic route quality monitoring
- Network topology analysis
- Route quality metrics and statistics

## Installation

### Prerequisites

- Python 3.13+
- Poetry (for dependency management)

### Setup

```bash
# Clone the repository
git clone <repository-url>
cd nhmesh-producer

# Install dependencies
poetry install

# Or with pip
pip install -r requirements.txt
```

## Usage

### Building Docker Image Locally

If you want to build the Docker image yourself instead of using the pre-built image:

```bash
# Build the image
docker build -t nhmesh-producer .

# Run the container
docker run -d \
    -e NODE_IP=192.168.1.100 \
    -e MQTT_USERNAME=your_username \
    -e MQTT_PASSWORD=your_password \
    -p 5001:5001 \
    nhmesh-producer
```


## Resilience Features

### Connection Management

- **Automatic reconnection** with exponential backoff
- **Health monitoring** every 30 seconds
- **Thread-safe operations** with proper locking
- **Graceful shutdown** with resource cleanup

### Error Handling

- **BrokenPipeError handling** for TCP connection failures
- **MQTT reconnection** on unexpected disconnections
- **Packet processing isolation** - errors don't crash the app
- **Fallback mechanisms** when services are unavailable

### Monitoring

- **Detailed logging** of connection events and recovery
- **Health check metrics** for connection quality
- **Error tracking** for adaptive behavior
- **Performance monitoring** with minimal overhead

## Testing

Run the resilience tests to verify the improvements:

```bash
python test_connection_resilience.py
```

The test suite verifies:

- Connection failure handling
- Reconnection logic
- Error isolation
- Graceful shutdown

## Troubleshooting

### Common Issues

1. **Connection failures**:

   - Check network connectivity to the Meshtastic node
   - Verify the node IP address is correct
   - Check firewall settings

2. **Frequent reconnections**:

   - Increase health check interval for less aggressive monitoring
   - Check network stability
   - Verify node is not rebooting frequently

3. **MQTT publish failures**:
   - Check MQTT broker connectivity
   - Verify credentials are correct
   - Check network connectivity to broker

### Debug Mode

Enable debug logging for detailed connection information:

```bash
export LOG_LEVEL=DEBUG
python -m nhmesh_producer.producer --node-ip 192.168.1.100
```

## Development

### Project Structure

```
nhmesh-producer/
├── nhmesh_producer/
│   ├── __init__.py
│   ├── producer.py          # Main producer logic
│   ├── web_interface.py     # Web interface and API
│   ├── utils/               # Utility functions
│   ├── templates/           # Web interface templates
│   └── schema.md           # Data schema documentation
├── pyproject.toml          # Project configuration
├── poetry.lock             # Dependency lock file
├── README.md               # This file
├── CONNECTION_RESILIENCE_IMPROVEMENTS.md  # Technical details
├── IMPROVEMENTS_SUMMARY.md # Quick reference
└── test_connection_resilience.py  # Test suite
```

### Adding Features

1. **New packet types**: Extend the packet processing in `producer.py`
2. **Web interface**: Add routes in `web_interface.py`
3. **Utilities**: Add helper functions in `utils/`
4. **Templates**: Add HTML templates in `templates/`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Submit a pull request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues and questions:

- Check the troubleshooting section above
- Review the connection resilience documentation
- Open an issue on GitHub

---

**Note**: This is a standalone producer extracted from the nhmesh-telemetry project, focusing specifically on the producer functionality with enhanced resilience features.
