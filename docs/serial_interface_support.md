# Serial Interface Support

The nhmesh-producer now supports both TCP and serial connections to Meshtastic nodes. This allows you to connect directly to a Meshtastic device via USB serial connection in addition to the existing TCP network connection.

## Connection Types

### TCP Connection (Default)

- Connects to a Meshtastic node over the network
- Requires the node to be running a TCP interface
- Uses the `--node-ip` parameter

### Serial Connection

- Connects directly to a Meshtastic device via USB serial
- Requires the device to be connected via USB
- Uses the `--serial-port` parameter

## Usage

### Command Line Arguments

```bash
# TCP Connection (default)
python -m nhmesh_producer.producer --node-ip 192.168.1.100

# Serial Connection
python -m nhmesh_producer.producer --connection-type serial --serial-port /dev/ttyUSB0

# With all options
python -m nhmesh_producer.producer \
  --connection-type serial \
  --serial-port /dev/ttyUSB0 \
  --broker mqtt.nhmesh.live \
  --topic msh/US/NH/
```

### Environment Variables

```bash
# TCP Connection
export NODE_IP="192.168.1.100"
export CONNECTION_TYPE="tcp"

# Serial Connection
export SERIAL_PORT="/dev/ttyUSB0"
export CONNECTION_TYPE="serial"
```

## Serial Port Configuration

### Linux

Common serial port names:

- `/dev/ttyUSB0` - USB-to-serial adapter
- `/dev/ttyACM0` - Arduino-style devices
- `/dev/ttyS0` - Built-in serial port

### macOS

Common serial port names:

- `/dev/tty.usbserial-*` - USB-to-serial adapters
- `/dev/tty.usbmodem*` - USB modems

### Windows

Common serial port names:

- `COM1`, `COM2`, etc. - Serial ports
- `COM3`, `COM4`, etc. - USB-to-serial adapters

## Finding Your Serial Port

### Linux

```bash
# List USB devices
lsusb

# List serial ports
ls /dev/tty*

# Check if device is connected
dmesg | grep tty
```

### macOS

```bash
# List serial ports
ls /dev/tty.*

# Check system information
system_profiler SPUSBDataType
```

### Windows

```bash
# List COM ports
mode

# Or check Device Manager for COM ports
```

## Testing Serial Connection

Use the provided test script to verify your serial connection:

```bash
# Set your serial port
export SERIAL_PORT="/dev/ttyUSB0"

# Run the test
python scripts/test_serial_connection.py
```

## Troubleshooting

### Common Issues

1. **Permission Denied**

   ```bash
   # Add user to dialout group (Linux)
   sudo usermod -a -G dialout $USER
   # Then log out and back in
   ```

2. **Port Not Found**

   - Check if the device is properly connected
   - Verify the correct port name
   - Try different port names (ttyUSB0, ttyACM0, etc.)

3. **Connection Timeout**

   - Ensure the Meshtastic device is powered on
   - Check that the device is not connected to another application
   - Try unplugging and reconnecting the USB cable

4. **Device Busy**
   - Close any other applications using the serial port
   - Check if Meshtastic is running on the device
   - Restart the Meshtastic device

### Debug Mode

Enable debug logging to see detailed connection information:

```bash
export LOG_LEVEL=DEBUG
python -m nhmesh_producer.producer --connection-type serial --serial-port /dev/ttyUSB0
```

## Configuration Examples

### Docker Compose with Serial

```yaml
version: "3.8"
services:
  nhmesh-producer:
    image: nhmesh-producer:latest
    environment:
      - CONNECTION_TYPE=serial
      - SERIAL_PORT=/dev/ttyUSB0
      - MQTT_ENDPOINT=mqtt.nhmesh.live
      - MQTT_TOPIC=msh/US/NH/
    devices:
      - /dev/ttyUSB0:/dev/ttyUSB0
    restart: unless-stopped
```

### Systemd Service with Serial

```ini
[Unit]
Description=NHMesh Producer
After=network.target

[Service]
Type=simple
User=nhmesh
Environment=CONNECTION_TYPE=serial
Environment=SERIAL_PORT=/dev/ttyUSB0
Environment=MQTT_ENDPOINT=mqtt.nhmesh.live
Environment=MQTT_TOPIC=msh/US/NH/
ExecStart=/usr/local/bin/nhmesh-producer
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Migration from TCP to Serial

If you're currently using TCP and want to switch to serial:

1. **Update your configuration:**

   ```bash
   # Old (TCP)
   export NODE_IP="192.168.1.100"

   # New (Serial)
   export CONNECTION_TYPE="serial"
   export SERIAL_PORT="/dev/ttyUSB0"
   ```

2. **Test the connection:**

   ```bash
   python scripts/test_serial_connection.py
   ```

3. **Update your deployment:**
   - Add USB device access to Docker containers
   - Update systemd services to include serial port access
   - Ensure proper permissions for the serial port

## Benefits of Serial Connection

1. **Direct Connection**: No network dependency
2. **Lower Latency**: Direct USB communication
3. **Reliability**: No network connectivity issues
4. **Simplicity**: No need for TCP server setup on the device
5. **Power Efficiency**: USB-powered devices can be more efficient

## Limitations

1. **Physical Connection**: Requires USB cable connection
2. **Port Availability**: Limited by available USB ports
3. **Distance**: Limited by USB cable length
4. **Platform Dependencies**: Serial port names vary by platform
