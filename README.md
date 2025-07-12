# NHMesh Producer

A resilient Meshtastic MQTT producer with automatic reconnection and connection health monitoring. This standalone producer handles the connection to Meshtastic nodes and publishes received packets to an MQTT broker with enhanced error handling and recovery mechanisms.

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

## Configuration

### Environment Variables

| Variable        | Description                | Default            |
| --------------- | -------------------------- | ------------------ |
| `MQTT_ENDPOINT` | MQTT broker address        | `mqtt.nhmesh.live` |
| `MQTT_PORT`     | MQTT broker port           | `1883`             |
| `MQTT_TOPIC`    | Root MQTT topic            | `msh/US/NH/`       |
| `MQTT_USERNAME` | MQTT username              | Required           |
| `MQTT_PASSWORD` | MQTT password              | Required           |
| `NODE_IP`       | Meshtastic node IP address | Required           |
| `WEB_HOST`      | Web interface host         | `0.0.0.0`          |
| `WEB_PORT`      | Web interface port         | `5001`             |
| `LOG_LEVEL`     | Logging level              | `INFO`             |

### Command Line Options

```bash
python -m nhmesh_producer.producer \
    --broker mqtt.nhmesh.live \
    --port 1883 \
    --topic msh/US/NH/ \
    --username your_username \
    --password your_password \
    --node-ip 192.168.1.100 \
    --web-interface \
    --web-host 0.0.0.0 \
    --web-port 5001
```

## Usage

### Basic Usage

```bash
# Start the producer with web interface
python -m nhmesh_producer.producer --node-ip 192.168.1.100

# Start without web interface
python -m nhmesh_producer.producer --node-ip 192.168.1.100 --no-web-interface
```

### Docker Usage

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

## Web Interface

The producer includes a web interface for real-time monitoring:

- **Dashboard**: Overview of network activity and statistics
- **Traceroute**: Visualize network topology and route quality
- **API Endpoints**: REST API for programmatic access to data

Access the web interface at: `http://localhost:5001`

### API Endpoints

- `GET /api/nodes` - List all discovered nodes
- `GET /api/recent_packets` - Recent packet history
- `GET /api/stats` - Network statistics
- `GET /api/traceroutes` - Traceroute data
- `GET /api/network-topology` - Network topology analysis

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
