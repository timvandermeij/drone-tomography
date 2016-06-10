import socket
import time
import random
import copy
import Queue
from core_thread_manager import ThreadableTestCase
from ..core.Thread_Manager import Thread_Manager
from ..zigbee.Packet import Packet
from ..zigbee.XBee_Sensor import SensorClosedError
from ..zigbee.XBee_Sensor_Simulator import XBee_Sensor_Simulator
from ..settings import Arguments
from settings import SettingsTestCase

class TestZigBeeXBeeSensorSimulator(ThreadableTestCase, SettingsTestCase):
    def location_callback(self):
        return (random.uniform(1.0, 50.0), random.uniform(1.0, 50.0)), random.randint(0, 5)

    def receive_callback(self, packet):
        pass

    def valid_callback(self, other_valid=None, other_id=None, other_index=None):
        return True

    def setUp(self):
        super(TestZigBeeXBeeSensorSimulator, self).setUp()

        self.sensor_id = 1
        self.arguments = Arguments("settings.json", ["--rf-sensor-id", "1"])
        self.settings = self.arguments.get_settings("xbee_sensor_simulator")
        self.thread_manager = Thread_Manager()
        self.sensor = XBee_Sensor_Simulator(self.arguments, self.thread_manager,
                                            None, self.location_callback,
                                            self.receive_callback, self.valid_callback)

        # Mock the activation of the sensor by calling `setup` ourselves and 
        # putting it in the active state. This does not actually start the 
        # sensor thread.
        self.sensor.setup()
        self.sensor._active = True

    def test_initialization(self):
        # The ID of the sensor must be set.
        self.assertEqual(self.sensor.id, self.sensor_id)

        # The next timestamp must be zero.
        self.assertEqual(self.sensor._next_timestamp, 0)

        # The location, receive and valid callbacks must be set.
        self.assertTrue(hasattr(self.sensor._location_callback, "__call__"))
        self.assertTrue(hasattr(self.sensor._receive_callback, "__call__"))
        self.assertTrue(hasattr(self.sensor._valid_callback, "__call__"))

        # The sweep data list must be empty.
        self.assertEqual(self.sensor._data, {})

        # The custom packet queue must be empty.
        self.assertIsInstance(self.sensor._queue, Queue.Queue)
        self.assertEqual(self.sensor._queue.qsize(), 0)

        # The sensor socket is set up by the call to `setup`.
        self.assertIsInstance(self.sensor._sensor, socket.socket)

    def test_get_identity(self):
        # The identity of the device must be returned as a dictionary.
        identity = self.sensor.get_identity()
        self.assertIsInstance(identity, dict)
        self.assertEqual(identity["id"], self.sensor_id)
        self.assertEqual(identity["address"], "{}:{}".format(self.sensor._ip, self.sensor._port))
        self.assertEqual(identity["joined"], True)

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

    def test_send(self):
        # After sending, the sweep data list must be empty.
        self.sensor._send()
        self.assertEqual(self.sensor._data, {})

    def test_send_custom_packets(self):
        # If the queue contains packets, some of them must be sent.
        packet = Packet()
        packet.set("specification", "waypoint_add")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("altitude", 0.0)
        packet.set("wait_id", 3)
        packet.set("index", 22)
        packet.set("to_id", 2)
        self.sensor.enqueue(packet, to=2)

        self.sensor._send_custom_packets()
        self.assertEqual(self.sensor._queue.qsize(), 0)

    def test_receive(self):
        # Create a packet from sensor 2 to the current sensor.
        packet = Packet()
        packet.set("specification", "rssi_broadcast")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("valid", True)
        packet.set("waypoint_index", 1)
        packet.set("sensor_id", 2)
        packet.set("timestamp", time.time())

        # After receiving that packet, the next timestamp must be synchronized.
        # Note that we must make a copy as the receive method will change the packet!
        copied_packet = copy.deepcopy(packet)
        self.sensor._receive(packet)
        self.assertEqual(self.sensor._next_timestamp,
                         self.sensor._scheduler.synchronize(copied_packet))

    def test_deactivate(self):
        # After deactivation the socket should be closed, and the sensor state 
        # should be cleared.
        sensor_socket = self.sensor._sensor
        self.sensor.deactivate()
        self.assertFalse(self.sensor._active)
        self.assertIsNone(self.sensor._sensor)
        with self.assertRaises(socket.error):
            sensor_socket.sendto("foo", ("127.0.0.1", 100))

    def test_deactivate_thread(self):
        # Actually start the sensor thread.
        self.sensor._active = False
        self.sensor.activate()

        self.assertEqual(self.thread_manager._threads, {
            "xbee_sensor": self.sensor
        })

        # Deactivate the thread.
        self.sensor.deactivate()

        self.assertEqual(self.thread_manager._threads, {})

        with self.assertRaises(SensorClosedError):
            self.sensor._send()
