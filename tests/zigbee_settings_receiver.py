import json
from StringIO import StringIO
from mock import Mock, mock_open, patch
from ..core.Thread_Manager import Thread_Manager
from ..settings import Settings
from ..zigbee.Packet import Packet
from ..zigbee.Settings_Receiver import Settings_Receiver
from ..zigbee.XBee_Sensor_Simulator import XBee_Sensor_Simulator
from environment import EnvironmentTestCase

class TestZigBeeSettingsReceiver(EnvironmentTestCase):
    def setUp(self):
        self.register_arguments([], use_infrared_sensor=False)

        super(TestZigBeeSettingsReceiver, self).setUp()

        self.rf_sensor = self.environment.get_rf_sensor()
        self.settings_receiver = self.environment._settings_receiver

    def test_setup(self):
        self.assertEqual(self.settings_receiver._environment, self.environment)
        self.assertEqual(self.settings_receiver._arguments, self.arguments)
        self.assertEqual(self.settings_receiver._rf_sensor, self.rf_sensor)
        self.assertEqual(self.settings_receiver._thread_manager, self.environment.thread_manager)
        self.assertEqual(self.settings_receiver._new_settings, {})
        self.assertIn("setting_clear", self.environment._packet_callbacks.keys())
        self.assertIn("setting_add", self.environment._packet_callbacks.keys())
        self.assertIn("setting_done", self.environment._packet_callbacks.keys())

    @patch.object(XBee_Sensor_Simulator, "enqueue")
    def test_clear(self, enqueue_mock):
        # Packets not meant for the current RF sensor are ignored.
        packet = Packet()
        packet.set("specification", "setting_clear")
        packet.set("to_id", self.rf_sensor.id + 42)

        self.environment.receive_packet(packet)
        self.assertNotEqual(Settings.settings_files, {})
        self.assertNotEqual(self.arguments.groups, {})
        enqueue_mock.assert_not_called()

        packet = Packet()
        packet.set("specification", "setting_clear")
        packet.set("to_id", self.rf_sensor.id)

        self.environment.receive_packet(packet)

        self.assertEqual(enqueue_mock.call_count, 1)
        args, kwargs = enqueue_mock.call_args
        self.assertEqual(len(args), 1)
        self.assertIsInstance(args[0], Packet)
        self.assertEqual(args[0].get_all(), {
            "specification": "setting_ack",
            "next_index": 0,
            "sensor_id": self.rf_sensor.id
        })
        self.assertEqual(kwargs, {"to": 0})

        self.assertEqual(Settings.settings_files, {})
        self.assertEqual(self.arguments.groups, {})

    @patch.object(XBee_Sensor_Simulator, "enqueue")
    def test_add(self, enqueue_mock):
        packet = Packet()
        packet.set("specification", "setting_add")
        packet.set("index", 0)
        packet.set("key", "home_location")
        packet.set("value", (1, 2))

        # Packets not meant for the current RF sensor are ignored.
        packet.set("to_id", self.rf_sensor.id + 42)

        self.environment.receive_packet(packet)
        self.assertNotIn("home_location", self.settings_receiver._new_settings)
        enqueue_mock.assert_not_called()

        packet.set("to_id", self.rf_sensor.id)

        self.environment.receive_packet(packet)

        self.assertEqual(enqueue_mock.call_count, 1)
        args, kwargs = enqueue_mock.call_args
        self.assertEqual(len(args), 1)
        self.assertIsInstance(args[0], Packet)
        self.assertEqual(args[0].get_all(), {
            "specification": "setting_ack",
            "next_index": 1,
            "sensor_id": self.rf_sensor.id
        })
        self.assertEqual(kwargs, {"to": 0})

        self.assertEqual(self.settings_receiver._new_settings, {
            "home_location": (1, 2)
        })

    @patch.object(Thread_Manager, "interrupt")
    def test_done(self, interrupt_mock):
        new_settings = {
            "home_location": (1, 2),
            "closeness": 0.0,
            "synchronize": True
        }
        pretty_json = json.dumps(new_settings, indent=4, sort_keys=True)
        self.settings_receiver._new_settings = new_settings

        # Packets not meant for the current RF sensor are ignored.
        packet = Packet()
        packet.set("specification", "setting_done")
        packet.set("to_id", self.rf_sensor.id + 42)
        self.environment.receive_packet(packet)
        self.assertNotEqual(Settings.settings_files, {})
        self.assertNotEqual(self.arguments.groups, {})

        packet = Packet()
        packet.set("specification", "setting_done")
        packet.set("to_id", self.rf_sensor.id)

        # Override the `open` function used in the settings receiver so that 
        # it does not actually write a file. Instead, make an Mock that 
        # simulated the open function. Additionally, attach a wrapper mock to 
        # the file's write function so that we can intercept the written data 
        # and check if it is correct.
        output = StringIO()
        open_mock = mock_open()
        write_mock = Mock(wraps=output.write)
        open_mock.return_value.attach_mock(write_mock, "write")
        open_func = '{}.open'.format(Settings_Receiver.__module__)
        with patch(open_func, open_mock, create=True):
            self.environment.receive_packet(packet)

        open_mock.assert_called_once_with(self.arguments.settings_file, 'w')
        self.assertEqual(output.getvalue(), pretty_json)

        self.assertEqual(Settings.settings_files, {})
        self.assertEqual(self.arguments.groups, {})
        interrupt_mock.assert_called_once_with("xbee_sensor")
