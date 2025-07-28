# NHMesh Producer

[![Poetry](https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json)](https://python-poetry.org/)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![PEP 8](https://img.shields.io/badge/code%20style-PEP%208-brightgreen.svg)](https://peps.python.org/pep-0008/)
[![Python](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/release/python-3130/)
[![Docker](https://img.shields.io/badge/docker-enabled-blue.svg)](https://www.docker.com/)
[![GHCR](https://img.shields.io/github/v/release/nhmesh/nhmesh-producer?logo=docker&logoColor=white&label=ghcr.io)](https://github.com/nhmesh/nhmesh-producer/pkgs/container/producer)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Build and Release](https://github.com/nhmesh/nhmesh-producer/workflows/Build%20and%20Release/badge.svg)](https://github.com/nhmesh/nhmesh-producer/actions/workflows/build-and-release.yml)
[![Test Build](https://github.com/nhmesh/nhmesh-producer/workflows/Test%20Build/badge.svg)](https://github.com/nhmesh/nhmesh-producer/actions/workflows/test-build.yml)

A resilient Meshtastic MQTT producer with automatic reconnection and connection health monitoring. This standalone producer handles the connection to Meshtastic nodes and publishes received packets to an MQTT broker with enhanced error handling and recovery mechanisms.

For information about contributing to this project, see [CONTRIBUTING.md](CONTRIBUTING.md).

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

| Variable                      | Default                      | Description                                                           |
| ----------------------------- | ---------------------------- | --------------------------------------------------------------------- |
| `LOG_LEVEL`                   | `INFO`                       | Logging level (DEBUG, INFO, WARNING, ERROR)                           |
| `MQTT_ENDPOINT`               | `mqtt.nhmesh.live`           | MQTT broker address                                                   |
| `MQTT_PORT`                   | `1883`                       | MQTT broker port                                                      |
| `MQTT_USERNAME`               | -                            | MQTT username for authentication                                      |
| `MQTT_PASSWORD`               | -                            | MQTT password for authentication                                      |
| `NODE_IP`                     | -                            | IP address of the Meshtastic node to connect to                       |
| `MQTT_TOPIC`                  | `msh/US/NH/`                 | Root MQTT topic for publishing messages                               |
| `TRACEROUTE_COOLDOWN`         | `180`                        | Minimum time between any traceroute operations in seconds (3 minutes) |
| `TRACEROUTE_INTERVAL`         | `43200`                      | Interval between periodic traceroutes in seconds (12 hours)           |
| `TRACEROUTE_MAX_RETRIES`      | `3`                          | Maximum number of retry attempts for failed traceroutes               |
| `TRACEROUTE_MAX_BACKOFF`      | `86400`                      | Maximum backoff time in seconds for failed nodes (24 hours)           |
| `TRACEROUTE_PERSISTENCE_FILE` | `/tmp/traceroute_state.json` | Path to file for persisting retry/backoff state across restarts       |

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

## Building Binaries

### Local Build

You can build binaries locally using the included build script:

```bash
# Build for current platform only
python3 build.py simple

# Build for all platforms (requires Docker)
python3 build.py docker

# Test existing binaries
python3 build.py test
```

### GitHub Actions

This project includes automated GitHub Actions workflows for building and releasing binaries. When you push a tag (e.g., `v1.0.0`), the workflow will automatically build binaries for all supported platforms and create a GitHub release.

**Supported Platforms:**

- Linux x86_64 (Intel/AMD servers and desktops)
- Linux ARM64 (Raspberry Pi, ARM servers)
- macOS x86_64 (Intel Macs)
- macOS ARM64 (Apple Silicon M1/M2)
- macOS Native (built on macOS runners)

For detailed information about the build process, release management, and contributing to the project, see [CONTRIBUTING.md](CONTRIBUTING.md).

### Downloading Pre-built Binaries

Pre-built binaries are available for all supported platforms on the [GitHub Releases](https://github.com/nhmesh/nhmesh-producer/releases) page. Simply download the appropriate binary for your platform and run it:

```bash
# Example for Linux x86_64
wget https://github.com/nhmesh/nhmesh-producer/releases/download/v1.0.0/nhmesh-producer-linux-x86_64.tar.gz
tar -xzf nhmesh-producer-linux-x86_64.tar.gz
./nhmesh-producer/nhmesh-producer --help
```

## Installation

### From Source

If you want to install from source or contribute to the project:

```bash
# Clone the repository
git clone https://github.com/nhmesh/nhmesh-producer.git
cd nhmesh-producer

# Install dependencies
poetry install

# Run the producer
poetry run python -m nhmesh_producer.producer \
    --username your_username \
    --password your_password \
    --node-ip 192.168.1.100
```

For detailed development setup instructions, see [CONTRIBUTING.md](CONTRIBUTING.md).

## Usage

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
