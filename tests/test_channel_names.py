
import unittest
from unittest.mock import MagicMock, patch
from nhmesh_producer.producer import MeshtasticMQTTHandler

class TestChannelNames(unittest.TestCase):
    def setUp(self):
        self.mock_interface = MagicMock()
        self.mock_interface.localNode.channels = []
        
        # Mock connection manager
        self.mock_conn_mgr_cls = patch('nhmesh_producer.producer.ConnectionManager').start()
        self.mock_conn_mgr = self.mock_conn_mgr_cls.return_value
        self.mock_conn_mgr.get_interface.return_value = self.mock_interface
        self.mock_conn_mgr.connect.return_value = True

        # Mock MQTT
        self.mock_mqtt_cls = patch('nhmesh_producer.producer.mqtt.Client').start()
        self.mock_mqtt_client = self.mock_mqtt_cls.return_value

        # Mock pubsub
        patch('nhmesh_producer.producer.pub').start()
        
        # Mock WebInterface
        patch('nhmesh_producer.producer.WebInterface').start()

    def tearDown(self):
        patch.stopall()

    def test_get_channel_map(self):
        # Setup channels
        ch0 = MagicMock()
        ch0.index = 0
        ch0.settings.name = "NHMesh"
        
        ch1 = MagicMock()
        ch1.index = 1
        ch1.settings.name = "MediumFast"
        
        ch2 = MagicMock()
        ch2.index = 2
        ch2.settings.name = "" # No name
        
        self.mock_interface.localNode.channels = [ch0, ch1, ch2]
        
        # Initialize handler (this calls get_channel_map)
        handler = MeshtasticMQTTHandler(
            broker="localhost", port=1883, topic="test", tls=False, 
            username=None, password=None, node_ip="1.2.3.4"
        )
        
        # Verify map
        expected_map = {0: "NHMesh", 1: "MediumFast"}
        self.assertEqual(handler.channel_map, expected_map)

    def test_on_receive_injects_name(self):
        # Setup handler with map
        handler = MeshtasticMQTTHandler(
            broker="localhost", port=1883, topic="test", tls=False, 
            username=None, password=None, node_ip="1.2.3.4"
        )
        handler.channel_map = {0: "NHMesh", 1: "MediumFast"}
        handler.channel_num = 0 # Default
        
        # Test packet on Ch 1
        packet = {
            "from": 123,
            "to": 456,
            "channel": 1,
            "payload": "test"
        }
        
        # Call onReceive
        handler.onReceive(packet, self.mock_interface)
        
        # Verify publish called with injected name
        args, _ = handler.mqtt_client.publish.call_args_list[0]
        # args[0] is topic, args[1] is payload (json string)
        import json
        payload = json.loads(args[1])
        
        self.assertEqual(payload.get("channelName"), "MediumFast")
        self.assertEqual(payload.get("channel_num"), 1)

    def test_on_receive_fallback_channel(self):
         # Setup handler with map
        handler = MeshtasticMQTTHandler(
            broker="localhost", port=1883, topic="test", tls=False, 
            username=None, password=None, node_ip="1.2.3.4"
        )
        handler.channel_map = {0: "NHMesh"}
        handler.channel_num = 0 # Default
        
        # Test packet with NO channel field
        packet = {
            "from": 123,
            "to": 456,
            "payload": "test"
        }
        
        # Call onReceive
        handler.onReceive(packet, self.mock_interface)
        
        # Verify publish used default channel num and name
        args, _ = handler.mqtt_client.publish.call_args_list[0]
        import json
        payload = json.loads(args[1])
        
        self.assertEqual(payload.get("channelName"), "NHMesh")
        self.assertEqual(payload.get("channel_num"), 0)

if __name__ == '__main__':
    unittest.main()
