from mock import MagicMock
from ..reconstruction.Stream_Buffer import Stream_Buffer
from ..settings import Arguments
from ..zigbee.Packet import Packet
from settings import SettingsTestCase

class TestReconstructionStreamBuffer(SettingsTestCase):
    def setUp(self):
        arguments = Arguments("settings.json", [
            "--stream-network-origin", "1", "1",
            "--stream-network-size", "15", "15",
            "--stream-calibrate"
        ])
        self.settings = arguments.get_settings("reconstruction_stream")
        self.mock_sensor = MagicMock(number_of_sensors=42)

        self.packet = Packet()
        self.packet.set("specification", "rssi_ground_station")
        self.packet.set("sensor_id", 1)
        self.packet.set("from_latitude", 1)
        self.packet.set("from_longitude", 0)
        self.packet.set("from_valid", True)
        self.packet.set("to_latitude", 1)
        self.packet.set("to_longitude", 10)
        self.packet.set("to_valid", True)
        self.packet.set("rssi", -38)

    def test_initialization(self):
        # Stream buffers are regular buffers with the exception that they
        # use settings to set the origin and size. Verify that these are
        # set correctly upon initialization. 
        stream_buffer = Stream_Buffer(self.settings)

        self.assertEqual(stream_buffer.number_of_sensors, 0)
        self.assertEqual(stream_buffer.origin, (1, 1))
        self.assertEqual(stream_buffer.size, (15, 15))

    def test_initialization_without_calibration(self):
        # When calibration mode is disabled, a calibration file for initial 
        # calibration must be provided.
        self.settings.set("stream_calibrate", False)
        with self.assertRaises(ValueError):
            stream_buffer = Stream_Buffer(self.settings)

        # A full path is allowed, and dump files also work.
        self.settings.set("stream_calibration_file", "tests/reconstruction/dump.json")
        stream_buffer = Stream_Buffer(self.settings)
        # The calibration initialization reads in all packets.
        self.assertEqual(len(stream_buffer._calibration), 2)

    def test_register_rf_sensor(self):
        # Stream buffers only know their number of sensors once an RF sensor is 
        # registered. This also registers the buffer in the RF sensor.
        stream_buffer = Stream_Buffer(self.settings)
        stream_buffer.register_rf_sensor(self.mock_sensor)

        self.assertEqual(stream_buffer.number_of_sensors, 42)
        self.mock_sensor.set_buffer.assert_called_once_with(stream_buffer)

    def test_get(self):
        stream_buffer = Stream_Buffer(self.settings)
        stream_buffer.register_rf_sensor(self.mock_sensor)

        # When the queue is empty, None should be returned.
        self.assertEqual(stream_buffer.get(), None)

        # If calibration mode is enabled, the original packet and RSSI value 
        # must be fetched.
        stream_buffer.put(self.packet)

        buffer_packet, buffer_calibrated_rssi = stream_buffer.get()
        self.assertEqual(buffer_packet.get_all(), {
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
        self.assertEqual(buffer_calibrated_rssi, -38)

    def test_get_with_calibration_file(self):
        # If calibration mode is disabled, the original packet and calibrated 
        # RSSI values must be fetched.
        self.settings.set("stream_calibrate", False)
        self.settings.set("stream_calibration_file",
                          "tests/reconstruction/stream_empty.json")
        stream_buffer = Stream_Buffer(self.settings)
        stream_buffer.register_rf_sensor(self.mock_sensor)
        stream_buffer.put(self.packet)

        buffer_packet, buffer_calibrated_rssi = stream_buffer.get()
        self.assertEqual(buffer_packet.get_all(), {
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
        self.assertEqual(buffer_calibrated_rssi, -38 - -34)
