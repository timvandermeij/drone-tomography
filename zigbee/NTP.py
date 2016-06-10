import os
import subprocess
import time
from Packet import Packet

class NTP(object):
    def __init__(self, sensor):
        """
        Initialize the NTP object. This object takes care of performing
        the NTP (network time protocol) algorithm.
        """

        self._sensor = sensor

    def start(self):
        """
        Start the NTP algorithm by sending the current time to the
        server (ground station) for synchronization.
        """

        # Construct the NTP packet.
        packet = Packet()
        packet.set("specification", "ntp")
        packet.set("sensor_id", self._sensor.id)
        packet.set("timestamp_1", time.time())
        packet.set("timestamp_2", 0)
        packet.set("timestamp_3", 0)
        packet.set("timestamp_4", 0)

        # Send the NTP packet to the ground station.
        self._sensor._send_tx_frame(packet, 0)

    def process(self, packet):
        """
        Process an incoming NTP packet `packet`. On the server (ground
        station) we set the second and third timestamps and send the
        result back to the client (sensor). The client (sensor) then
        takes care of finishing the NTP algorithm execution.
        """

        if packet.get("timestamp_2") == 0:
            packet.set("timestamp_2", time.time())
            packet.set("timestamp_3", time.time())
            self._sensor._send_tx_frame(packet, packet.get("sensor_id"))
        else:
            packet.set("timestamp_4", time.time())
            self.finish(packet)

    def finish(self, packet):
        """
        Finish the NTP algorithm to synchronize the clock of the client
        (sensor) with the clock of the server (ground station).

        Refer to the original paper "Internet time synchronization: the
        network time protocol" by David L. Mills (IEEE, 1991) for more
        information.
        """

        # Calculate the clock offset.
        a = packet.get("timestamp_2") - packet.get("timestamp_1")
        b = packet.get("timestamp_3") - packet.get("timestamp_4")
        clock_offset = float(a + b) / 2

        # Apply the offset to the current clock to synchronize.
        synchronized = time.time() + clock_offset

        # Update the system clock with the synchronized clock.
        with open(os.devnull, 'w') as FNULL:
            subprocess.call(["date", "-s", "@{}".format(synchronized)],
                            stdout=FNULL, stderr=FNULL)

        self._sensor._synchronized = True
        return clock_offset
