"""Shared mesh-fleet contract (Meshtastic side)."""
import unittest
from unittest.mock import MagicMock, patch

from meshtastic.protobuf import channel_pb2, config_pb2, localonly_pb2

from nhmesh_producer import fleet_contract as fc
from nhmesh_producer import web_interface as wi


def fake_node():
    n = MagicMock()
    n.localConfig = localonly_pb2.LocalConfig()
    n.moduleConfig = localonly_pb2.LocalModuleConfig()
    n.localConfig.lora.region = config_pb2.Config.LoRaConfig.RegionCode.US
    n.localConfig.lora.modem_preset = config_pb2.Config.LoRaConfig.ModemPreset.MEDIUM_FAST
    n.localConfig.lora.tx_power = 27
    n.moduleConfig.mqtt.address = "mqtt.nhmesh.live"
    ch = channel_pb2.Channel(index=0)
    ch.settings.name = "NHMesh"
    n.channels = [ch]
    return n


class TestReadWrite(unittest.TestCase):
    def test_read_normalised(self):
        self.assertEqual(fc.read_config(fake_node()), {
            "region": "US", "modem_preset": "MEDIUM_FAST", "tx_power": 27, "role": "CLIENT",
            "primary_channel": "NHMesh", "mqtt_address": "mqtt.nhmesh.live"})

    def test_write_touches_only_needed_sections(self):
        n = fake_node()
        applied = fc.write_config(n, {"tx_power": 20, "role": "CLIENT_MUTE"}, timeout=2)
        self.assertEqual(applied, {"tx_power": "ok", "role": "ok"})
        self.assertEqual(n.localConfig.lora.tx_power, 20)
        self.assertEqual([c.args[0] for c in n.writeConfig.call_args_list], ["lora", "device"])
        n.writeChannel.assert_not_called()

    def test_write_rejects_unknown_keys(self):
        with self.assertRaises(ValueError):
            fc.write_config(fake_node(), {"psk": "x"}, timeout=2)

    def test_admin_refusal_maps_to_needs_admin_key(self):
        def refuse():
            raise RuntimeError("Error: ADMIN_PUBLIC_KEY_UNAUTHORIZED")
        with self.assertRaises(fc.NeedsAdminKey):
            fc._with_timeout(refuse, 2)


class TestRoutes(unittest.TestCase):
    def setUp(self):
        self.iface = MagicMock()
        self.iface.localNode = fake_node()
        handler = MagicMock()
        handler.connection_manager.get_interface.return_value = self.iface
        self.client = wi.WebInterface(handler).app.test_client()

    def test_self_config_route(self):
        r = self.client.get("/api/nodes/self/config")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["config"]["modem_preset"], "MEDIUM_FAST")

    def test_remote_without_admin_key_is_403(self):
        with patch.object(fc, "resolve", side_effect=fc.NeedsAdminKey("nope")):
            r = self.client.get("/api/nodes/!2b24a8d9/config")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.get_json()["result_type"], "NEEDS_ADMIN_KEY")

    def test_token_required_except_health(self):
        with patch.object(wi, "API_TOKEN", "t0k"):
            self.assertEqual(self.client.get("/api/nodes/self/config").status_code, 401)
            ok = self.client.get("/api/nodes/self/config", headers={"Authorization": "Bearer t0k"})
            self.assertEqual(ok.status_code, 200)
            self.assertNotEqual(self.client.get("/api/health").status_code, 401)


class TestTelemetry(unittest.TestCase):
    def setUp(self):
        fc._telemetry.clear()
        self.iface = MagicMock()
        self.iface.getMyNodeInfo.return_value = {"user": {"id": "!7c5ccbd0"}}
        self.iface.nodes = {"!2b24a8d9": {"lastHeard": 1000.0, "deviceMetrics": {"voltage": 3.9, "batteryLevel": 80}}}

    def status(self, now):
        return fc.node_status(self.iface, "!2b24a8d9", now=lambda: now)

    def test_requests_hourly_and_dates_the_reading(self):
        with patch.object(fc, "request_telemetry", return_value={"voltage": 3.64, "batteryLevel": 41}) as req:
            st = self.status(1100.0)
            self.assertEqual((st["voltage"], st["battery_level"], st["telemetry_time"]), (3.64, 41, 1100))
            self.status(1100.0 + 1800)       # within the hour: cached, no new request
            self.assertEqual(req.call_count, 1)
            self.iface.nodes["!2b24a8d9"]["lastHeard"] = 1100.0 + 3600
            self.status(1100.0 + 3700)       # an hour later: asks again
            self.assertEqual(req.call_count, 2)

    def test_undated_node_db_value_has_no_telemetry_time(self):
        with patch.object(fc, "request_telemetry", side_effect=TimeoutError("no reply")):
            st = self.status(1100.0)
        self.assertEqual(st["voltage"], 3.9)
        self.assertIsNone(st["telemetry_time"])

    def test_never_asks_a_node_not_heard_recently(self):
        with patch.object(fc, "request_telemetry") as req:
            self.status(1000.0 + 7 * 3600)
        req.assert_not_called()

    def test_a_failed_request_is_not_retried_every_poll(self):
        with patch.object(fc, "request_telemetry", side_effect=TimeoutError("no reply")) as req:
            self.status(1100.0)
            self.status(1220.0)
        self.assertEqual(req.call_count, 1)

    def test_request_waits_for_metrics_not_a_routing_reply(self):
        iface = MagicMock()
        def send(*a, **kw):
            kw["onResponse"]({"decoded": {"portnum": "ROUTING_APP"}})
            kw["onResponse"]({"decoded": {"telemetry": {"deviceMetrics": {"voltage": 3.7}}}})
        iface.sendData.side_effect = send
        self.assertEqual(fc.request_telemetry(iface, "!2b24a8d9", timeout=1), {"voltage": 3.7})
