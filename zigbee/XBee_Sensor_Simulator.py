import random
import socket
import thread
import time
from Packet import Packet
from XBee_Sensor import XBee_Sensor, SensorClosedError

class XBee_Sensor_Simulator(XBee_Sensor):
    def __init__(self, arguments, thread_manager, usb_manager,
                 location_callback, receive_callback, valid_callback):
        """
        Initialize the simulated XBee sensor.
        """

        self._type = "xbee_sensor_simulator"

        super(XBee_Sensor_Simulator, self).__init__(arguments, thread_manager, usb_manager,
                                                    location_callback, receive_callback, valid_callback)

        self._joined = True
        self._ip = self._settings.get("ip")
        self._port = self._settings.get("socket_port")

    def setup(self):
        """
        Setup a unique, non-blocking UDP socket connection.
        """

        self._sensor = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sensor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sensor.bind((self._ip, self._port + self._id))
        self._sensor.setblocking(0)

    def activate(self):
        """
        Activate the sensor to send and receive packets.
        """

        super(XBee_Sensor_Simulator, self).activate()

        if not self._active:
            self._active = True

            if self._sensor is None:
                self.setup()

            thread.start_new_thread(self._loop, ())

    def _loop(self):
        """
        Execute the sensor loop. This runs in a separate thread.
        """

        try:
            buffer_size = self._settings.get("buffer_size")

            while self._active:
                # If the sensor has been activated, this loop will only send
                # enqueued custom packets. If the sensor has been started, we
                # stop sending custom packets and start performing signal
                # strength measurements.
                if not self._started:
                    self._send_custom_packets()
                    time.sleep(self._custom_packet_delay)
                elif self._id > 0 and time.time() >= self._next_timestamp:
                    self._next_timestamp = self._scheduler.get_next_timestamp()
                    self._send()
                    time.sleep(self._loop_delay)

                # Check if there is data to be processed.
                try:
                    data = self._sensor.recv(buffer_size)
                except AttributeError:
                    # Socket was removed by deactivate, so end the loop.
                    break
                except socket.error:
                    time.sleep(self._loop_delay)
                    continue

                # Unserialize the data (byte-encoded string).
                packet = Packet()
                packet.unserialize(data)
                self._receive(packet)
        except SensorClosedError:
            # Socket was removed by deactivate, so end the loop.
            pass
        except:
            super(XBee_Sensor_Simulator, self).interrupt()

    def deactivate(self):
        """
        Deactivate the sensor by closing the socket.
        """

        super(XBee_Sensor_Simulator, self).deactivate()

        if self._active or self._sensor is not None:
            self._active = False

            if self._sensor is not None:
                # Close the sensor and clean up so that the thread might get 
                # the signal faster and we can correctly reactivate later on.
                self._sensor.close()
                self._sensor = None

    def discover(self, callback):
        """
        Discover other XBee devices in the network.

        This method is only used on the ground station in the control panel
        to refresh the status of the other XBee devices.
        """

        # The simulator does not use XBee device discovery because it does not
        # use the actual XBee library that provides this functionality. We
        # simulate the process by calling the callback with the packet manually.
        for vehicle in xrange(1, self._number_of_sensors + 1):
            callback({
                "id": self._id + vehicle,
                "address": "{}:{}".format(self._ip, self._port + self._id + vehicle)
            })

    def _send(self):
        """
        Send packets to all other sensors in the network.
        """

        for i in xrange(1, self._number_of_sensors + 1):
            if i == self._id:
                continue

            packet = self._make_rssi_broadcast_packet()
            self._send_tx_frame(packet, i)

        # Send the sweep data to the ground sensor.
        for frame_id in self._data.keys():
            packet = self._data[frame_id]
            self._send_tx_frame(packet, 0)
            self._data.pop(frame_id)

    def _send_tx_frame(self, packet, to=None):
        """
        Send a TX frame to another sensor.
        """

        super(XBee_Sensor_Simulator, self)._send_tx_frame(packet, to)

        serialized_packet = packet.serialize()

        try:
            self._sensor.sendto(serialized_packet, (self._ip, self._port + to))
        except AttributeError:
            raise SensorClosedError

    def _receive(self, packet):
        """
        Receive and process packets from all other sensors in the network.
        """

        if not self._check_receive(packet):
            if self._id > 0:
                self._next_timestamp = self._scheduler.synchronize(packet)

                # Create and complete the packet for the ground station.
                ground_station_packet = self._make_rssi_ground_station_packet(packet)
                ground_station_packet.set("rssi", -random.randint(30, 70))
                frame_id = chr(random.randint(1, 255))
                self._data[frame_id] = ground_station_packet
            elif self._buffer is not None:
                self._buffer.put(packet)

    def _format_address(self, address):
        """
        Pretty print a given address.
        """

        address = "{}:{}".format(self._ip, self._port)
        return address.upper()
