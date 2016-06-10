import time
from ..zigbee.Packet import Packet
from ..zigbee.TDMA_Scheduler import TDMA_Scheduler
from ..settings import Arguments
from settings import SettingsTestCase

class TestZigBeeTDMAScheduler(SettingsTestCase):
    def setUp(self):
        self.id = 2

        self.arguments = Arguments("settings.json", ["--number-of-sensors", "8"])
        self.settings = self.arguments.get_settings("zigbee_tdma_scheduler")

        self.scheduler = TDMA_Scheduler(self.id, self.settings)

        self.number_of_sensors = self.settings.get("number_of_sensors")
        self.sweep_delay = self.settings.get("sweep_delay")

    def test_initialization(self):
        # Verify that only `Settings` and `Arguments` objects can be used to initialize.
        TDMA_Scheduler(self.id, self.arguments)
        TDMA_Scheduler(self.id, self.settings)
        with self.assertRaises(ValueError):
            TDMA_Scheduler(self.id, None)

        # The ID of the sensor must be set.
        self.assertEqual(self.scheduler.id, self.id)

        # The initial timestamp must be zero for synchronization purposes.
        self.assertEqual(self.scheduler.timestamp, 0)

    def test_get_next_timestamp(self):
        # The first time the get_next_timestamp() method is called, the next
        # timestamp is based on the current time c. If the total sweep takes t
        # seconds, then the next timestamp is calculated as c + (i / n) * t,
        # where i is the ID of the sensor and n is the total number of sensors
        # in the network. This formula assures that each sensor gets an equally
        # large time slot in the sweep.
        calculated = self.scheduler.get_next_timestamp()
        correct = time.time() + ((float(self.id) / self.number_of_sensors) *
                                 self.sweep_delay)
        self.assertAlmostEqual(calculated, correct, delta=0.1)

        # Any subsequent calls to the get_next_timestamp() method should just
        # increase the previous timestamp (which might have been updated in the
        # meantime by the synchronize() method) with the sweep delay to move
        # to the next sweep.
        calculated = self.scheduler.get_next_timestamp()
        correct = correct + self.sweep_delay
        self.assertAlmostEqual(calculated, correct, delta=0.1)

    def test_synchronize(self):
        # If the received packet is from a sensor with a lower ID than the
        # current sensor, then the next timestamp for the current sensor should
        # be calculated as the timestamp in the received packet plus the number
        # of slots inbetween them. For example, if sensor 2 receives a packet from
        # sensor 1, then sensor 2 must start sending right after sensor 1, i.e., the
        # timestamp for sensor 2 is the timestamp of sensor 1 plus the time required
        # for one slot, defined as the total sweep time divided by the number
        # of sensors in the network.
        packet = Packet()
        packet.set("specification", "rssi_broadcast")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("valid", True)
        packet.set("waypoint_index", 1)
        packet.set("sensor_id", 1)
        packet.set("timestamp", time.time())

        calculated = self.scheduler.synchronize(packet)
        slot_time = float(self.sweep_delay) / self.number_of_sensors
        correct = packet.get("timestamp") + ((self.id - packet.get("sensor_id")) * slot_time)
        self.assertEqual(calculated, correct)

        # If the received packet is from a sensor with a higher ID than the
        # current sensor, then the next timestamp for the current sensor should
        # be calculated as the timestamp in the received packet plus the number
        # of slots required to complete the current sweep plus the number of slots
        # required before the current sensor is allowed to start transmitting.
        # For example, if sensor 2 receives a packet from sensor 6 and the total
        # number of slots is 8, then 8 - 6 + 1 = 3 slots are required to complete
        # the current sweep (as we need a full slot for sensors 6, 7 and 8).
        # We then need to add 2 - 1 = 1 slot for sensor 1 and then sensor 2 is
        # allowed to start.
        packet = Packet()
        packet.set("specification", "rssi_broadcast")
        packet.set("latitude", 123456789.12)
        packet.set("longitude", 123459678.34)
        packet.set("valid", True)
        packet.set("waypoint_index", 2)
        packet.set("sensor_id", 6)
        packet.set("timestamp", time.time())

        calculated = self.scheduler.synchronize(packet)
        completed_round = (self.number_of_sensors - packet.get("sensor_id") + 1) * slot_time
        correct = packet.get("timestamp") + completed_round + ((self.id - 1) * slot_time)
        self.assertEqual(calculated, correct)
