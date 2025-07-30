import meshtastic.tcp_interface

try:
    interface = meshtastic.tcp_interface.TCPInterface(hostname="10.250.1.103")
    # Attempt to send a small, non-disruptive message or request
    # For example, requesting node info might be a good "ping"
    interface.getMyNodeInfo()
    print("TCP connection appears to be alive and responsive.")
except (OSError, ConnectionRefusedError, TimeoutError) as e:
    print(f"TCP connection is not alive or responsive: {e}")
finally:
    if "interface" in locals() and interface.socket:
        interface.close()
