import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path so we can import nhmesh_producer
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from nhmesh_producer.producer import MeshtasticMQTTHandler

class TestDisconnectLoop(unittest.TestCase):
    @patch('nhmesh_producer.producer.ConnectionManager')
    @patch('nhmesh_producer.producer.pub')
    @patch('nhmesh_producer.producer.mqtt')
    def test_stale_disconnect_ignored(self, mock_mqtt, mock_pub, mock_conn_manager_cls):
        """Test that onDisconnect ignores events from stale interfaces."""
        
        # Setup mocks
        mock_conn_manager = mock_conn_manager_cls.return_value
        
        # Create two mock interfaces
        stale_interface = MagicMock()
        stale_interface.name = "stale_interface"
        
        current_interface = MagicMock()
        current_interface.name = "current_interface"
        
        # Configure ConnectionManager to return the current interface
        mock_conn_manager.get_interface.return_value = current_interface
        mock_conn_manager.interface = current_interface
        # A property mock might be needed if the code accesses .interface directly
        # But looking at the code, it calls get_interface() inside ConnectionManager, 
        # but in producer.py onDisconnect check (which we will implement), we'll likely compare against 
        # connection_manager.get_interface() or a cached reference.
        
        # Instantiate the handler
        # We need to mock the arguments to __init__ to avoid actual connections
        handler = MeshtasticMQTTHandler(
            broker="localhost",
            port=1883,
            topic="test/topic",
            tls=False,
            username=None,
            password=None,
            serial_port="/dev/ttyUSB0",
            connection_type="serial"
        )
        
        # Mock handle_external_error
        handler.connection_manager.handle_external_error = MagicMock()
        
        print("\n--- Testing Stale Interface Disconnect ---")
        # trigger onDisconnect with the STALE interface
        # This simulates the "Disconnect" event from the OLD connection arriving late
        handler.onDisconnect(stale_interface, "Connection lost")
        
        # ASSERTION: handle_external_error should NOT be called
        # If the bug exists, this assertion will fail (it WILL be called)
        # If the fix is implemented, this assertion will pass
        if handler.connection_manager.handle_external_error.call_count > 0:
            print("FAILURE: handle_external_error WAS called for stale interface!")
        else:
            print("SUCCESS: handle_external_error was NOT called for stale interface.")
            
        handler.connection_manager.handle_external_error.assert_not_called()
        
        print("\n--- Testing Valid Interface Disconnect ---")
        # trigger onDisconnect with the CURRENT interface
        handler.onDisconnect(current_interface, "Connection lost")
        
        # ASSERTION: handle_external_error SHOULD be called
        if handler.connection_manager.handle_external_error.call_count == 1:
             print("SUCCESS: handle_external_error WAS called for current interface.")
        else:
             print(f"FAILURE: handle_external_error call count: {handler.connection_manager.handle_external_error.call_count}")

        handler.connection_manager.handle_external_error.assert_called_once()


if __name__ == '__main__':
    unittest.main()
