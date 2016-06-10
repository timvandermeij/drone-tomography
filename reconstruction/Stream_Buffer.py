import json
from Buffer import Buffer

class Stream_Buffer(Buffer):
    def __init__(self, settings=None):
        """
        Initialize the stream buffer object.
        """

        super(Stream_Buffer, self).__init__(settings)

        self._origin = settings.get("stream_network_origin")
        self._size = settings.get("stream_network_size")

        self._calibrate = settings.get("stream_calibrate")

        # Read the data from the empty network (for calibration).
        if not self._calibrate:
            calibration_filename = settings.get("stream_calibration_file")
            if calibration_filename is None:
                raise ValueError("If calibration mode is disabled, then a calibration file must be provided.")

            with open(calibration_filename, "r") as stream_calibration_file:
                data = json.load(stream_calibration_file)

                for packet in data["packets"]:
                    source = (packet[1], packet[2])
                    destination = (packet[4], packet[5])

                    if packet[3] and packet[6]:
                        key = (source, destination)
                        if key not in self._calibration:
                            self._calibration[key] = packet[7]

    def register_rf_sensor(self, rf_sensor):
        """
        Register the buffer in the RF sensor `rf_sensor`, and request the number
        of sensors from it.
        """

        self._number_of_sensors = rf_sensor.number_of_sensors
        rf_sensor.set_buffer(self)

    def get(self):
        """
        Get a packet from the buffer (or None if the queue is empty). The return
        value is a tuple of the original packet and the calibrated RSSI value.
        If calibration mode is enabled, however, we return the original RSSI
        value because there is no complete calibration yet.
        """

        if self._queue.empty():
            return None

        packet = self._queue.get()

        if self._calibrate:
            # We are in calibration mode. There is no complete calibration yet,
            # so return the original packet and original RSSI value.
            return (packet, packet.get("rssi"))

        source = (packet.get("from_latitude"), packet.get("from_longitude"))
        destination = (packet.get("to_latitude"), packet.get("to_longitude"))
        calibrated_rssi = packet.get("rssi") - self._calibration[(source, destination)]

        return (packet, calibrated_rssi)
