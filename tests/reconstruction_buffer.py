import unittest
from ..reconstruction.Buffer import Buffer
from ..zigbee.Packet import Packet

class TestReconstructionBuffer(unittest.TestCase):
    def setUp(self):
        self.buffer = Buffer({})

        # Create a list of unique packets.
        self.packets = []
        self.packets_count = 3

        for index in range(self.packets_count):
            packet = Packet()
            packet.set("specification", "rssi_ground_station")
            packet.set("sensor_id", 1)
            packet.set("from_latitude", 12.3456789)
            packet.set("from_longitude", 21.3456789)
            packet.set("from_valid", True)
            packet.set("to_latitude", 13.4567892)
            packet.set("to_longitude", 14.4567892)
            packet.set("to_valid", True)
            packet.set("rssi", index)

            self.packets.append(packet)

    def test_initialization(self):
        # If no options have been provided, an error should be raised.
        # Note that the `setUp` method already covers the case where
        # options have been provided.
        with self.assertRaises(ValueError):
            Buffer()

    def test_get(self):
        # If the buffer is empty, we should get None.
        self.assertEqual(self.buffer.get(), None)

        # If the buffer is not empty, we should get the first item.
        for packet in self.packets:
            self.buffer.put(packet)

        for index in range(self.packets_count):
            self.assertEqual(self.buffer.get(), self.packets[index])

        self.assertEqual(self.buffer.get(), None)

    def test_put(self):
        # Invalid packets should not be inserted.
        with self.assertRaises(ValueError):
            self.buffer.put("foo")

        # Valid packets should be inserted.
        self.buffer.put(self.packets[0])
        self.assertEqual(self.buffer.get(), self.packets[0])

    def test_count(self):
        self.assertEqual(self.buffer.count(), 0)

        for packet in self.packets:
            self.buffer.put(packet)

        self.assertEqual(self.buffer.count(), self.packets_count)

    def test_number_of_sensors(self):
        self.assertEqual(self.buffer.number_of_sensors, 0)

    def test_origin(self):
        self.assertEqual(self.buffer.origin, (0, 0))

    def test_size(self):
        self.assertEqual(self.buffer.size, (0, 0))
