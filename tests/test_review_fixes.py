"""Regression tests for the 2026-10 producer review fixes."""

import argparse
import unittest
from unittest.mock import MagicMock, patch

import paho.mqtt.client as mqtt
from paho.mqtt.packettypes import PacketTypes
from paho.mqtt.reasoncodes import ReasonCode

from nhmesh_producer.producer import (
    MeshtasticMQTTHandler,
    modem_preset_name,
    node_topic_id,
    str2bool,
)
from nhmesh_producer.utils.connection_manager import ConnectionManager


class TestHelpers(unittest.TestCase):
    def test_modem_preset_names(self):
        self.assertEqual(modem_preset_name(0), "LongFast")
        self.assertEqual(modem_preset_name(4), "MediumFast")
        self.assertEqual(modem_preset_name(6), "ShortFast")
        self.assertEqual(modem_preset_name(999), "Unknown")

    def test_str2bool(self):
        self.assertFalse(str2bool("false"))  # bool("false") is True — the old bug
        self.assertFalse(str2bool("0"))
        self.assertTrue(str2bool("TRUE"))
        self.assertTrue(str2bool(True))
        with self.assertRaises(argparse.ArgumentTypeError):
            str2bool("maybe")

    def test_node_topic_id(self):
        self.assertEqual(node_topic_id({"fromId": "!7c5b3a28"}), "!7c5b3a28")
        self.assertEqual(node_topic_id({"from": 2086353448}), "!7c5b3a28")
        self.assertEqual(node_topic_id({}), "unknown")


class TestConnectionManager(unittest.TestCase):
    def test_get_interface_does_not_reconnect(self):
        cm = ConnectionManager(serial_port="/dev/null", connection_type="serial")
        with patch.object(cm, "reconnect") as reconnect:
            self.assertIsNone(cm.get_interface())
            reconnect.assert_not_called()

    def test_close_and_status_without_health_thread(self):
        cm = ConnectionManager(serial_port="/dev/null", connection_type="serial")
        self.assertFalse(cm.get_health_status()["health_monitor_alive"])
        cm.close()  # used to raise AttributeError: 'NoneType' has no 'is_alive'


class HandlerTestBase(unittest.TestCase):
    def setUp(self):
        self.iface = MagicMock()
        self.iface.localNode.channels = []
        self.iface.localNode.localConfig.lora.modem_preset = 4
        self.iface.localNode.localConfig.lora.channel_num = 0
        cm_cls = patch("nhmesh_producer.producer.ConnectionManager").start()
        self.cm = cm_cls.return_value
        self.cm.connect.return_value = True
        self.cm.get_interface.return_value = self.iface
        self.cm.connected_node_id = "!7c5b3a28"
        self.mqtt_cls = patch("nhmesh_producer.producer.mqtt.Client").start()
        self.mqtt_client = self.mqtt_cls.return_value
        patch("nhmesh_producer.producer.pub").start()
        patch("nhmesh_producer.producer.WebInterface").start()
        self.tr_cls = patch("nhmesh_producer.producer.TracerouteManager").start()
        self.nc_cls = patch("nhmesh_producer.producer.NodeCache").start()

    def tearDown(self):
        patch.stopall()

    def make(self, **kw):
        args = dict(
            broker="localhost",
            port=1883,
            topic="msh/US/NH/",
            tls=False,
            username=None,
            password=None,
            serial_port="/dev/usbport-1.2",
            connection_type="serial",
        )
        args.update(kw)
        return MeshtasticMQTTHandler(**args)


class TestHandler(HandlerTestBase):
    def test_single_connection_at_startup(self):
        h = self.make()
        self.cm.connect.assert_called_once()
        self.assertEqual(h.modem_preset, "MediumFast")

    def test_initial_connect_retries_then_succeeds(self):
        self.cm.connect.side_effect = [False, True]
        with patch("nhmesh_producer.producer.INITIAL_CONNECT_BACKOFF_SEC", 0):
            self.make()
        self.assertEqual(self.cm.connect.call_count, 2)

    def test_initial_connect_gives_up(self):
        self.cm.connect.return_value = False
        with patch("nhmesh_producer.producer.INITIAL_CONNECT_BACKOFF_SEC", 0):
            with self.assertRaises(Exception):
                self.make()

    def test_paho_v2_and_reconnect_policy(self):
        self.make(tls=True)
        self.mqtt_cls.assert_called_once_with(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.reconnect_delay_set.assert_called_once()
        self.mqtt_client.tls_set.assert_called_once()

    def test_disconnect_does_not_spawn_reconnect_threads(self):
        h = self.make()
        h.mqtt_connected = True
        rc = ReasonCode(PacketTypes.DISCONNECT, "Unspecified error")
        with patch("nhmesh_producer.producer.threading.Thread") as thread:
            h._on_mqtt_disconnect(self.mqtt_client, None, None, rc, None)
            thread.assert_not_called()
        self.assertFalse(h.mqtt_connected)
        self.mqtt_client.reconnect.assert_not_called()

    def test_publish_uses_qos1(self):
        h = self.make()
        self.mqtt_client.publish.return_value.rc = mqtt.MQTT_ERR_SUCCESS
        h.publish_dict_to_mqtt({"from": 1, "decoded": {}})
        topic, payload = self.mqtt_client.publish.call_args[0][:2]
        self.assertEqual(topic, "msh/US/NH//!00000001")
        self.assertEqual(self.mqtt_client.publish.call_args.kwargs.get("qos"), 1)

    def test_no_traceroute_to_own_node(self):
        h = self.make()
        h.node_cache.update_from_packet.return_value = True
        h._update_cache_from_packet({"fromId": "!7c5b3a28"})
        h.traceroute_manager.process_packet_for_traceroutes.assert_not_called()
        h._update_cache_from_packet({"fromId": "!a4db5209"})
        h.traceroute_manager.process_packet_for_traceroutes.assert_called_once_with(
            "!a4db5209", True
        )


if __name__ == "__main__":
    unittest.main()



class TestEnvDefault(unittest.TestCase):
    """The --tls crash-loop (2026-10-24): a falsy default made the flag required."""

    def _parser(self):
        from nhmesh_producer.utils.envdefault import EnvDefault

        p = argparse.ArgumentParser()
        p.add_argument("--tls", type=str2bool, default=False, action=EnvDefault, envvar="T_TLS")
        p.add_argument("--port", type=int, default=0, action=EnvDefault, envvar="T_PORT")
        p.add_argument("--user", action=EnvDefault, envvar="T_USER")
        return p

    def test_falsy_defaults_are_not_required(self):
        with patch.dict("os.environ", {}, clear=True):
            args = self._parser().parse_args(["--user", "u"])
        self.assertFalse(args.tls)
        self.assertEqual(args.port, 0)

    def test_env_value_is_type_converted(self):
        with patch.dict("os.environ", {"T_TLS": "false", "T_USER": "u"}, clear=True):
            self.assertFalse(self._parser().parse_args([]).tls)

    def test_no_default_still_required(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit):
                self._parser().parse_args([])
