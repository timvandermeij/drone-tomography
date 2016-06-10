# Core imports
import Queue
import random
import time

# Library imports
import serial
from xbee import ZigBee
from mock import patch

# Package imports
from ..core.Thread_Manager import Thread_Manager
from ..zigbee.Packet import Packet
from ..zigbee.XBee_Sensor import SensorClosedError
from ..zigbee.XBee_Sensor_Physical import XBee_Sensor_Physical
from ..settings import Arguments
from core_thread_manager import ThreadableTestCase
from core_usb_manager import USBManagerTestCase
from settings import SettingsTestCase

class TestZigBeeXBeeSensorPhysical(USBManagerTestCase, ThreadableTestCase, SettingsTestCase):
    def location_callback(self):
        return (random.uniform(1.0, 50.0), random.uniform(1.0, 50.0)), random.randint(0, 5)

    def receive_callback(self, packet):
        pass

    def valid_callback(self, other_valid=None, other_id=None, other_index=None):
        return True

    def setUp(self):
        super(TestZigBeeXBeeSensorPhysical, self).setUp()

        self.sensor_id = 1

        self.arguments = Arguments("settings.json", ["--port", self._xbee_port])
        self.settings = self.arguments.get_settings("xbee_sensor_physical")
        self.thread_manager = Thread_Manager()

        self.usb_manager.index()
        self.sensor = XBee_Sensor_Physical(self.arguments, self.thread_manager,
                                           self.usb_manager, self.location_callback,
                                           self.receive_callback, self.valid_callback)
        self.sensor._id = self.sensor_id

    def tearDown(self):
        # Ensure the sensor is deactivated for tests that use `mock_setup` but 
        # do not deactivate it themselves.
        self.sensor.deactivate()

        super(TestZigBeeXBeeSensorPhysical, self).tearDown()

    def mock_setup(self):
        """
        Mock the activation of the XBee sensor by setting it up and enabling
        various flags that skip join checks. This does not actually start the
        sensor loop thread.
        """

        # Set all status variables to True to avoid being stuck in
        # the join loops. We cannot test the join process in the unit tests.
        self.sensor._node_identifier_set = True
        self.sensor._address_set = True
        self.sensor._joined = True
        self.sensor._synchronized = True

        # The serial connection and sensor must be initialized.
        self.sensor.setup()
        self.sensor._active = True

    def test_initialization(self):
        self.assertEqual(self.sensor.id, self.sensor_id)
        self.assertTrue(hasattr(self.sensor._location_callback, "__call__"))
        self.assertTrue(hasattr(self.sensor._receive_callback, "__call__"))
        self.assertTrue(hasattr(self.sensor._valid_callback, "__call__"))
        self.assertEqual(self.sensor._next_timestamp, 0)
        self.assertEqual(self.sensor._serial_connection, None)
        self.assertEqual(self.sensor._node_identifier_set, False)
        self.assertEqual(self.sensor._address_set, False)
        self.assertEqual(self.sensor._joined, False)
        self.assertEqual(self.sensor._synchronized, False)
        self.assertEqual(self.sensor._sensor, None)
        self.assertEqual(self.sensor._address, None)
        self.assertEqual(self.sensor._data, {})
        self.assertIsInstance(self.sensor._queue, Queue.Queue)
        self.assertEqual(self.sensor._queue.qsize(), 0)

    def test_get_identity(self):
        # The identity of the device must be returned as a dictionary.
        identity = self.sensor.get_identity()
        self.assertIsInstance(identity, dict)
        self.assertEqual(identity["id"], self.sensor_id)
        self.assertEqual(identity["address"], "-")
        self.assertEqual(identity["joined"], False)

    def test_setup(self):
        self.mock_setup()

        # The serial connection and sensor must be initialized.
        self.assertIsInstance(self.sensor._serial_connection, serial.Serial)
        self.assertIsInstance(self.sensor._sensor, ZigBee)
        self.assertEqual(self.sensor._node_identifier_set, True)
        self.assertEqual(self.sensor._address_set, True)
        self.assertEqual(self.sensor._joined, True)
        self.assertEqual(self.sensor._synchronized, True)

    def test_deactivate(self):
        self.mock_setup()

        # After deactivation the serial connection must be closed.
        # Note that this also means that the sensor object is halted, and the 
        # sensor state is cleared.
        self.sensor.deactivate()
        self.assertFalse(self.sensor._active)
        self.assertIsNone(self.sensor._serial_connection)
        with self.assertRaises(SensorClosedError):
            self.sensor._send()

    def test_enqueue(self):
        # Packets that are not `Packet` objects should be refused.
        with self.assertRaises(TypeError):
            self.sensor.enqueue({
                "foo": "bar"
            })

        # Private packets should be refused.
        with self.assertRaises(ValueError):
            packet = Packet()
            packet.set("specification", "rssi_broadcast")
            self.sensor.enqueue(packet)

        # Packets that do not contain a destination should be broadcasted.
        # We subtract one because we do not send to ourself.
        packet = Packet()
        packet.set("specification", "waypoint_add")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("altitude", 0.0)
        packet.set("wait_id", 3)
        packet.set("index", 22)
        packet.set("to_id", 2)
        self.sensor.enqueue(packet)
        self.assertEqual(self.sensor._queue.qsize(),
                         self.settings.get("number_of_sensors") - 1)
        self.sensor._queue = Queue.Queue()

        # Valid packets should be enqueued.
        packet = Packet()
        packet.set("specification", "waypoint_add")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("altitude", 0.0)
        packet.set("wait_id", 3)
        packet.set("index", 22)
        packet.set("to_id", 2)
        self.sensor.enqueue(packet, to=2)
        self.assertEqual(self.sensor._queue.get(), {
            "packet": packet,
            "to": 2
        })

    @patch("xbee.ZigBee.send")
    def test_send(self, mock_send):
        self.sensor._address = "sensor_{}".format(self.sensor_id)

        # Activate the sensor and ignore any _send() calls as we are not
        # interested in the initialization calls.
        self.mock_setup()
        mock_send.call_count = 0

        # Packets must be sent to all other sensors except the ground sensor
        # and itself (the latter explains the subtraction of one).
        self.sensor._send()
        self.assertEqual(mock_send.call_count,
                         self.settings.get("number_of_sensors") - 1)

        # If the data object contains valid packets (i.e., the RSSI value is
        # not None), then they must be sent to the ground station. We expect
        # the same number of calls as before, but with one additional call
        # for transmitting the valid packet. After transmission, the packet
        # should be removed from the data object.
        mock_send.call_count = 0
        valid_packet = Packet()
        valid_packet.set("specification", "rssi_ground_station")
        valid_packet.set("sensor_id", self.sensor_id)
        valid_packet.set("from_latitude", 123456789.12)
        valid_packet.set("from_longitude", 123456789.12)
        valid_packet.set("from_valid", True)
        valid_packet.set("to_latitude", 123456789.12)
        valid_packet.set("to_longitude", 123456789.12)
        valid_packet.set("to_valid", True)
        valid_packet.set("rssi", 56)
        self.sensor._data = {
            42: valid_packet
        }
        self.sensor._send()
        self.assertEqual(mock_send.call_count,
                         self.settings.get("number_of_sensors"))
        self.assertNotIn(42, self.sensor._data)

    @patch("xbee.ZigBee.send")
    def test_send_custom_packets(self, mock_send):
        self.sensor._address = "sensor_{}".format(self.sensor_id)

        # Activate the sensor and ignore any _send() calls as we are not
        # interested in the initialization calls.
        self.mock_setup()
        self.sensor._active = True
        mock_send.call_count = 0

        # If the queue contains custom packets, some of them must be sent.
        packet = Packet()
        packet.set("specification", "waypoint_add")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("altitude", 0.0)
        packet.set("wait_id", 3)
        packet.set("index", 22)
        packet.set("to_id", 2)
        self.sensor.enqueue(packet, to=2)

        queue_length = self.sensor._queue.qsize()
        self.sensor._send_custom_packets()
        self.assertEqual(mock_send.call_count, queue_length)
        self.assertEqual(self.sensor._queue.qsize(), 0)

    def test_receive(self):
        self.mock_setup()

        # Valid RX packets should be processed. Store the frame ID
        # for the DB call test following this test.
        packet = Packet()
        packet.set("specification", "rssi_broadcast")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("valid", True)
        packet.set("waypoint_index", 1)
        packet.set("sensor_id", 2)
        packet.set("timestamp", time.time())
        raw_packet = {
            "id": "rx",
            "rf_data": packet.serialize()
        }
        self.sensor._receive(raw_packet)
        frame_id = None
        for key in self.sensor._data.iterkeys():
            frame_id = key

        # Check if the received packet is valid.
        original_packet = self.sensor._data[frame_id]
        self.assertNotEqual(original_packet.get("from_latitude"), None)
        self.assertNotEqual(original_packet.get("from_longitude"), None)
        self.assertNotEqual(original_packet.get("to_latitude"), None)
        self.assertNotEqual(original_packet.get("to_longitude"), None)
        self.assertEqual(original_packet.get("rssi"), None)

        # AT response DB packets should be processed. The parsed RSSI value
        # should be placed in the original packet in the data object.
        raw_packet = {
            "id": "at_response",
            "frame_id": frame_id,
            "command": "DB",
            "parameter": "\x4E"
        }
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._data[frame_id].get("rssi"), -ord("\x4E"))

    def test_receive_at_network_packets(self):
        # AT response SH packets should be processed.
        self.sensor._address_set = False
        raw_packet = {
            "id": "at_response",
            "command": "SH",
            "parameter": "high"
        }
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._address, "high")

        # If a low part is already present in the address, the high
        # part should be prepended.
        self.sensor._address = "low"
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._address, "highlow")
        self.assertEqual(self.sensor._address_set, True)

        # If the high part is already present in the address (due to
        # a repeated request), it should not be prepended again.
        self.sensor._address = "highlow"
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._address, "highlow")

        # AT response SL packets should be processed.
        self.sensor._address_set = False
        self.sensor._address = None
        raw_packet = {
            "id": "at_response",
            "command": "SL",
            "parameter": "low"
        }
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._address, "low")

        # If a high part is already present in the address, the low
        # part should be appended.
        self.sensor._address = "high"
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._address, "highlow")
        self.assertEqual(self.sensor._address_set, True)

        # If the low part is already present in the address (due to
        # a repeated request), it should not be appended again.
        self.sensor._address = "highlow"
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._address, "highlow")

        # AT response NI packets should be processed.
        self.sensor._node_identifier_set = False
        raw_packet = {
            "id": "at_response",
            "command": "NI",
            "parameter": "4"
        }
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor.id, 4)
        self.assertEqual(self.sensor._scheduler.id, 4)
        self.assertEqual(self.sensor._node_identifier_set, True)

        # AT response AI failure packets should be processed.
        self.sensor._joined = False
        raw_packet = {
            "id": "at_response",
            "command": "AI",
            "parameter": "\x01"
        }
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._joined, False)

        # AT response AI success packets should be processed.
        raw_packet = {
            "id": "at_response",
            "command": "AI",
            "parameter": "\x00"
        }
        self.sensor._receive(raw_packet)
        self.assertEqual(self.sensor._joined, True)

    @patch.object(XBee_Sensor_Physical, "_receive", side_effect=ValueError)
    @patch.object(XBee_Sensor_Physical, "_error")
    def test_receive_error(self, error_mock, receive_mock):
        packet = Packet()
        packet.set("specification", "rssi_broadcast")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("valid", True)
        packet.set("waypoint_index", 1)
        packet.set("sensor_id", 2)
        packet.set("timestamp", time.time())
        raw_packet = {
            "id": "rx",
            "rf_data": packet.serialize()
        }

        # Patch the frame reading method of xbee.ZigBee to return our raw 
        # packet so that we can check that the receive mock gets this packet.
        # Patch the start method of xbee.ZigBee so that it does not acutally 
        # start the thread, so we get a deterministic number of calls in the 
        # run method of xbee.ZigBee.
        with patch.object(ZigBee, "wait_read_frame", return_value=raw_packet):
            with patch.object(ZigBee, "start"):
                self.mock_setup()
                self.sensor._sensor.run()

                receive_mock.assert_called_once_with(raw_packet)

                # Ensure that the error mock receives the exception from the 
                # receive mock.
                self.assertEqual(error_mock.call_count, 1)
                self.assertIsInstance(error_mock.call_args[0][0], ValueError)
