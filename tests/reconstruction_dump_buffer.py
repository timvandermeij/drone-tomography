from ..reconstruction.Dump_Buffer import Dump_Buffer
from ..settings import Arguments
from settings import SettingsTestCase

class TestReconstructionDumpBuffer(SettingsTestCase):
    def setUp(self):
        # Dump buffers are regular buffers with the exception that they
        # populate the queue with packets read from a JSON data file.
        # Verify that these are set correctly upon initialization.
        # We mock the `Settings.check_format` method so that we can pass test 
        # files instead of assets to the arguments.
        arguments = Arguments("settings.json", [
            "--dump-calibration-file", "tests/reconstruction/dump_empty.json",
            "--dump-file", "tests/reconstruction/dump.json"
        ])
        settings = arguments.get_settings("reconstruction_dump")
        self.dump_buffer = Dump_Buffer(settings)

    def test_initialization(self):
        self.assertEqual(self.dump_buffer.number_of_sensors, 2)
        self.assertEqual(self.dump_buffer.origin, (0, 0))
        self.assertEqual(self.dump_buffer.size, (10, 10))

        self.assertEqual(self.dump_buffer.count(), 2)

        # The calibration RSSI value for the link must be subtracted
        # from the originally measured RSSI value.
        first_packet, first_calibrated_rssi = self.dump_buffer.get()
        self.assertEqual(first_packet.get_all(), {
            "specification": "rssi_ground_station",
            "sensor_id": 1,
            "from_latitude": 1,
            "from_longitude": 0,
            "from_valid": True,
            "to_latitude": 1,
            "to_longitude": 10,
            "to_valid": True,
            "rssi": -38
        })
        self.assertEqual(first_calibrated_rssi, -38 - -36)

        second_packet, second_calibrated_rssi = self.dump_buffer.get()
        self.assertEqual(second_packet.get_all(), {
            "specification": "rssi_ground_station",
            "sensor_id": 2,
            "from_latitude": 0,
            "from_longitude": 2,
            "from_valid": True,
            "to_latitude": 6,
            "to_longitude": 10,
            "to_valid": True,
            "rssi": -41
        })
        self.assertEqual(second_calibrated_rssi, -41 - -38)

        self.assertEqual(self.dump_buffer.get(), None)
        self.assertEqual(self.dump_buffer.count(), 0)

    def test_put(self):
        # Verify that only lists can be put in the buffer.
        with self.assertRaises(ValueError):
            self.dump_buffer.put(42)

        # Verify that only lists of valid length can be put in the buffer.
        with self.assertRaises(ValueError):
            self.dump_buffer.put([1, 2])
