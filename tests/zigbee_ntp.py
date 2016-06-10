import time
import unittest
from mock import MagicMock, patch
from ..zigbee.NTP import NTP
from ..zigbee.Packet import Packet

class TestZigBeeNTP(unittest.TestCase):
    def setUp(self):
        # Mock the sensor.
        self._sensor = MagicMock()
        self._sensor.id = 1

        self._ntp = NTP(self._sensor)

    def test_start(self):
        # Verify that the ground station packet is sent.
        self._ntp.start()

        self.assertEqual(self._sensor._send_tx_frame.call_count, 1)
        arguments = self._sensor._send_tx_frame.call_args[0]

        self.assertEqual(len(arguments), 2)
        packet = arguments[0]
        to = arguments[1]
        self.assertEqual(packet.get("specification"), "ntp")
        self.assertEqual(packet.get("sensor_id"), 1)
        self.assertAlmostEqual(packet.get("timestamp_1"), time.time(), delta=0.1)
        self.assertEqual(packet.get("timestamp_2"), 0)
        self.assertEqual(packet.get("timestamp_3"), 0)
        self.assertEqual(packet.get("timestamp_4"), 0)
        self.assertEqual(to, 0)

    @patch.object(NTP, "finish")
    def test_process(self, mock_finish):
        # Construct the NTP packet for the second and third timestamp.
        packet = Packet()
        packet.set("specification", "ntp")
        packet.set("sensor_id", self._sensor.id)
        packet.set("timestamp_1", 42)
        packet.set("timestamp_2", 0)
        packet.set("timestamp_3", 0)
        packet.set("timestamp_4", 0)

        # Verify that the second and third timestamps are set.
        self._ntp.process(packet)

        self.assertEqual(self._sensor._send_tx_frame.call_count, 1)
        arguments = self._sensor._send_tx_frame.call_args[0]

        self.assertEqual(len(arguments), 2)
        packet = arguments[0]
        to = arguments[1]
        self.assertEqual(packet.get("specification"), "ntp")
        self.assertEqual(packet.get("sensor_id"), self._sensor.id)
        self.assertEqual(packet.get("timestamp_1"), 42)
        self.assertAlmostEqual(packet.get("timestamp_2"), time.time(), delta=0.1)
        self.assertAlmostEqual(packet.get("timestamp_3"), time.time(), delta=0.1)
        self.assertEqual(packet.get("timestamp_4"), 0)
        self.assertEqual(to, packet.get("sensor_id"))

        # Construct the NTP packet for the fourth timestamp.
        packet = Packet()
        packet.set("specification", "ntp")
        packet.set("sensor_id", self._sensor.id)
        packet.set("timestamp_1", 42)
        packet.set("timestamp_2", 43)
        packet.set("timestamp_3", 43)
        packet.set("timestamp_4", 0)

        # Verify that the fourth timestamp is set.
        self._ntp.process(packet)

        self.assertEqual(mock_finish.call_count, 1)
        arguments = mock_finish.call_args[0]

        self.assertEqual(len(arguments), 1)
        packet = arguments[0]
        self.assertEqual(packet.get("specification"), "ntp")
        self.assertEqual(packet.get("sensor_id"), self._sensor.id)
        self.assertEqual(packet.get("timestamp_1"), 42)
        self.assertEqual(packet.get("timestamp_2"), 43)
        self.assertEqual(packet.get("timestamp_3"), 43)
        self.assertAlmostEqual(packet.get("timestamp_4"), time.time(), delta=0.1)

    @patch("subprocess.call")
    def test_finish(self, mock_subprocess_call):
        # Construct a complete NTP packet.
        packet = Packet()
        packet.set("specification", "ntp")
        packet.set("sensor_id", 1)
        packet.set("timestamp_1", 100)
        packet.set("timestamp_2", 150)
        packet.set("timestamp_3", 160)
        packet.set("timestamp_4", 120)

        # Verify that the clock offset is correctly calculated.
        clock_offset = self._ntp.finish(packet)
        self.assertEqual(clock_offset, 45)
        self.assertEqual(mock_subprocess_call.call_count, 1)
