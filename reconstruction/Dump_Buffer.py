import json
from Buffer import Buffer
from ..zigbee.Packet import Packet

class Dump_Buffer(Buffer):
    def __init__(self, settings=None):
        """
        Initialize the dump buffer object.
        """

        super(Dump_Buffer, self).__init__(settings)

        # Read the data from the empty network (for calibration).
        # Note that the indices used here correspond to the fields in the
        # RSSI ground station packet (in order).
        calibration_filename = settings.get("dump_calibration_file")
        with open(calibration_filename, "r") as dump_calibration_file:
            data = json.load(dump_calibration_file)

            for packet in data["packets"]:
                source = (packet[1], packet[2])
                destination = (packet[4], packet[5])

                if packet[3] and packet[6]:
                    key = (source, destination)
                    if key not in self._calibration:
                        self._calibration[key] = packet[7]

        # Read the provided dump file. The JSON file has the following structure:
        #
        # - number_of_sensors: number of sensors in the network (excluding ground station)
        # - origin: a list containing the coordinates of the network's origin
        # - size: a list containing the width and height of the network
        # - packets: a list containing one list per packet, where each packet list
        #            contains the data from the packet specification
        #            "rssi_ground_station" (in order)
        with open(settings.get("dump_file"), "r") as dump_file:
            data = json.load(dump_file)

            self._number_of_sensors = data["number_of_sensors"]
            self._origin = tuple(data["origin"])
            self._size = tuple(data["size"])

            for packet in data["packets"]:
                self.put(packet)

    def get(self):
        """
        Get a packet from the buffer (or None if the queue is empty). We create
        the `Packet` object from the list on demand (as further explained
        in the `put` method). The return value is a tuple of the original packet
        and the calibrated RSSI value.
        """

        if self._queue.empty():
            return None

        dump = self._queue.get()

        packet = Packet()
        packet.set("specification", "rssi_ground_station")
        packet.set_dump(dump)

        source = (packet.get("from_latitude"), packet.get("from_longitude"))
        destination = (packet.get("to_latitude"), packet.get("to_longitude"))
        calibrated_rssi = packet.get("rssi") - self._calibration[(source, destination)]

        return (packet, calibrated_rssi)

    def put(self, packet):
        """
        Put a packet into the buffer. The difference with the base class method
        is that a packet is not a `Packet` object, but instead a list that
        contains the data from the packet fields in order. `Packet` objects
        are generated from this information on demand in the `get` method. This
        optimization is required because the dumps typically contain many
        measurements, making creating all `Packet` objects at once very
        time-consuming.
        """

        if not isinstance(packet, list) or len(packet) != 8:
            raise ValueError("The provided packet is not a valid list.")

        self._queue.put(packet)
