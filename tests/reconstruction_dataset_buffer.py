from ..reconstruction.Dataset_Buffer import Dataset_Buffer
from ..settings import Arguments
from settings import SettingsTestCase

class TestReconstructionDatasetBuffer(SettingsTestCase):
    def setUp(self):
        # The sensor ID and RSSI values come from the CSV file.
        self.sensor_id = 5
        self.calibration = [
            -62, -63, -58, -59, -49, -45, -58, -59, -56, -53, -57, -54, -60, -56,
            -62, -70, -60, -63, -68, -66, -67, -70, -64, -60, -62, -62, -54, -60
        ]
        self.rssi = [
            -63, -62, -60, -59, -52, -45, -58, -60, -61, -52, -58, -54, -60, -60,
            -62, -70, -60, -62, -66, -66, -67, -70, -68, -61, -62, -62, -54, -60
        ]

        # The size and positions come from the Utah dataset specification.
        self.size = (21, 21)
        self.positions = [
            (0, 0), (0, 3), (0, 6), (0, 9), (0, 12), (0, 15), (0, 18),
            (0, 21), (3, 21), (6, 21), (9, 21), (12, 21), (15, 21), (18, 21),
            (21, 21), (21, 18), (21, 15), (21, 12), (21, 9), (21, 6), (21, 3),
            (21, 0), (18, 0), (15, 0), (12, 0), (9, 0), (6, 0), (2, 0)
        ]

        # Dataset buffers are regular buffers with the exception that they
        # populate the queue with packets read from a CSV data file.
        # Verify that these are set correctly upon initialization.
        # We mock the `Settings.check_format` method so that we can pass test 
        # files instead of assets to the arguments.
        arguments = Arguments("settings.json", [
            "--dataset-calibration-file", "tests/reconstruction/dataset_empty.csv",
            "--dataset-file", "tests/reconstruction/dataset.csv"
        ])
        settings = arguments.get_settings("reconstruction_dataset")
        self.dataset_buffer = Dataset_Buffer(settings)

    def test_initialization(self):
        self.assertEqual(self.dataset_buffer.number_of_sensors, len(self.positions))
        self.assertEqual(self.dataset_buffer.origin, (0, 0))
        self.assertEqual(self.dataset_buffer.size, self.size)

        # One data point is ignored because a sensor cannot send to itself.
        self.assertEqual(self.dataset_buffer.count(), len(self.positions) - 1)

        for index in range(len(self.positions)):
            if index == self.sensor_id:
                continue

            packet, calibrated_rssi = self.dataset_buffer.get()
            self.assertEqual(packet.get_all(), {
                "specification": "rssi_ground_station",
                "sensor_id": self.sensor_id + 1,
                "from_latitude": self.positions[index][0],
                "from_longitude": self.positions[index][1],
                "from_valid": True,
                "to_latitude": self.positions[self.sensor_id][0],
                "to_longitude": self.positions[self.sensor_id][1],
                "to_valid": True,
                "rssi": self.rssi[index]
            })
            self.assertEqual(calibrated_rssi, self.rssi[index] - self.calibration[index])

        self.assertEqual(self.dataset_buffer.get(), None)
        self.assertEqual(self.dataset_buffer.count(), 0)

    def test_put(self):
        # Verify that only lists can be put in the buffer.
        with self.assertRaises(ValueError):
            self.dataset_buffer.put(42)

        # Verify that only lists of valid length can be put in the buffer.
        with self.assertRaises(ValueError):
            self.dataset_buffer.put([1, 2])
