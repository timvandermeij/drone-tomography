import struct
import unittest
from ..zigbee.Packet import Packet

class TestZigBeePacket(unittest.TestCase):
    def setUp(self):
        self.packet = Packet()

    def test_initialization(self):
        # The packet must be empty.
        self.assertEqual(self.packet._contents, {})

        # The specifications dictionary must be set.
        self.assertIsInstance(self.packet._specifications, dict)

        # The packet must be private by default.
        self.assertTrue(self.packet._private)

    def test_set(self):
        # A given key and value should be present in the contents.
        self.packet.set("foo", "bar")
        self.assertEqual(self.packet._contents["foo"], "bar")

        # When an invalid specification is set, the private property
        # must not be updated.
        private = self.packet._private
        self.packet.set("specification", "foo")
        self.assertEqual(private, self.packet._private)

        # When a valid specification is set, the private property
        # must be updated.
        self.packet.set("specification", "waypoint_add")
        self.assertFalse(self.packet._private)

    def test_unset(self):
        # A given key should not be present in the contents.
        self.packet._contents["foo"] = "bar"
        self.packet.unset("foo")
        self.assertNotIn("foo", self.packet._contents)

        # Verify that unsetting a nonexistent key does not throw
        # a KeyError, but instead does nothing.
        self.packet.unset("foo")

    def test_get(self):
        # The value of a present key should be fetched.
        self.packet._contents["foo"] = "bar"
        self.assertEqual(self.packet.get("foo"), "bar")

        # "None" should be returned for a nonexistent key.
        self.assertEqual(self.packet.get("quux"), None)

    def test_get_all(self):
        # All contents should be fetched.
        self.packet._contents["foo"] = "bar"
        self.packet._contents["baz"] = "quux"
        self.assertEqual(self.packet.get_all(), {
            "foo": "bar",
            "baz": "quux"
        })

    def test_get_dump(self):
        # Packets other than RSSI ground station packets should not be accepted.
        packet = Packet()
        packet.set("specification", "waypoint_clear")
        packet.set("to_id", 5)
        with self.assertRaises(ValueError):
            packet.get_dump()

        # RSSI ground station packets should be accepted. The return value should
        # be a list of all values in the same order as the specification.
        packet = Packet()
        packet.set("specification", "rssi_ground_station")
        packet.set("sensor_id", 1)
        packet.set("from_latitude", 2)
        packet.set("from_longitude", 3)
        packet.set("from_valid", True)
        packet.set("to_latitude", 4)
        packet.set("to_longitude", 5)
        packet.set("to_valid", False)
        packet.set("rssi", 67)
        self.assertEqual(packet.get_dump(), [1, 2, 3, True, 4, 5, False, 67])

    def test_set_dump(self):
        dump = [1, 2, 3, True, 4, 5, False, 67]

        # Packets other than RSSI ground station packets should not be accepted.
        packet = Packet()
        packet.set("specification", "waypoint_clear")
        packet.set("to_id", 5)
        with self.assertRaises(ValueError):
            packet.set_dump(dump)

        # RSSI ground station packets should be accepted. We verify that all
        # fields are set correctly.
        packet = Packet()
        packet.set("specification", "rssi_ground_station")
        packet.set_dump(dump)

        self.assertEqual(packet.get_all(), {
            "specification": "rssi_ground_station",
            "sensor_id": 1,
            "from_latitude": 2,
            "from_longitude": 3,
            "from_valid": True,
            "to_latitude": 4,
            "to_longitude": 5,
            "to_valid": False,
            "rssi": 67
        })

    def test_serialize(self):
        # A specification must be provided.
        with self.assertRaises(KeyError):
            self.packet.serialize()

        # A provided specification must exist.
        self.packet.set("specification", "foo")
        with self.assertRaises(KeyError):
            self.packet.serialize()

        # All fields from the specification must be provided.
        self.packet.set("specification", "waypoint_add")
        with self.assertRaises(KeyError):
            self.packet.serialize()

        # All fields from the specification must be serializable.
        self.packet.set("specification", "setting_done")
        self.packet.set("to_id", "2") # String instead of integer
        with self.assertRaises(ValueError):
            self.packet.serialize()

        # When all fields are provided, the specification field must be
        # unset and the packed message must be valid.
        self.packet.set("specification", "waypoint_add")
        self.packet.set("latitude", 123456789.12)
        self.packet.set("longitude", 123496785.34)
        self.packet.set("altitude", 4.2)
        self.packet.set("wait_id", 3)
        self.packet.set("index", 22)
        self.packet.set("to_id", 2)
        packed_message = self.packet.serialize()
        self.assertEqual(packed_message,
                         "\x06H\xe1zT4o\x9dA\xf6(\\E\xa5q\x9dA\xcd\xcc\xcc\xcc\xcc\xcc\x10@\x03\x16\x00\x00\x00\x02")

    def test_serialize_object_packed(self):
        self.packet.set("specification", "setting_add")
        self.packet.set("index", 0)
        self.packet.set("key", "bar")
        self.packet.set("value", 42)
        self.packet.set("to_id", 1)

        packed_message = self.packet.serialize()
        self.assertEqual(packed_message, "\n\x00\x00\x00\x00\x03bar\x01i*\x00\x00\x00\x01")

    def test_serialize_object_compressed(self):
        self.packet.set("specification", "setting_add")
        self.packet.set("index", 1)
        self.packet.set("key", "items")
        self.packet.set("value", [1, 2, 3])
        self.packet.set("to_id", 1)

        packed_message = self.packet.serialize()
        self.assertEqual(packed_message,
                         "\n\x01\x00\x00\x00\x05items\x00\x11x\x9c\x8b6\xd4Q0\xd2Q0\x8e\x05\x00\t\x85\x01\xe7\x01")

    def test_unserialize(self):
        # Empty strings must be refused.
        with self.assertRaises(struct.error):
            self.packet.unserialize("")

        # Invalid specifications must be refused.
        with self.assertRaises(KeyError):
            self.packet.unserialize("\xFF\x01")

        # All fields from the specification must be unserializable.
        with self.assertRaises(ValueError):
            self.packet.unserialize("\n\x00\x00\x00\x00\x03bar") # Final part of packet missing

        # Reset the packet as the previous test changed some fields in the packet.
        self.packet = Packet()

        # Valid messages must be unpacked.
        message = "\x06H\xe1zT4o\x9dA\xf6(\\E\xa5q\x9dA\xcd\xcc\xcc\xcc\xcc\xcc\x10@\x03\x16\x00\x00\x00\x02"
        self.packet.unserialize(message)
        self.assertEqual(self.packet.get_all(), {
            "specification": "waypoint_add",
            "latitude": 123456789.12,
            "longitude": 123496785.34,
            "altitude": 4.2,
            "wait_id": 3,
            "index": 22,
            "to_id": 2
        })
        self.assertFalse(self.packet.is_private())

    def test_unserialize_object_packed(self):
        self.packet.unserialize("\n\x00\x00\x00\x00\x03bar\x01i*\x00\x00\x00\x01")
        self.assertEqual(self.packet.get_all(), {
            "specification": "setting_add",
            "index": 0,
            "key": "bar",
            "value": 42,
            "to_id": 1
        })
        self.assertFalse(self.packet.is_private())

    def test_unserialize_object_compressed(self):
        message = "\n\x01\x00\x00\x00\x05items\x00\x11x\x9c\x8b6\xd4Q0\xd2Q0\x8e\x05\x00\t\x85\x01\xe7\x01"
        self.packet.unserialize(message)
        self.assertEqual(self.packet.get_all(), {
            "specification": "setting_add",
            "index": 1,
            "key": "items",
            "value": [1, 2, 3],
            "to_id": 1
        })
        self.assertFalse(self.packet.is_private())

    def test_is_private(self):
        # The private property should be returned.
        private = self.packet.is_private()
        self.assertEqual(self.packet._private, private)
