import random
import struct
import thread
import time
from xbee import ZigBee
from NTP import NTP
from Packet import Packet
from XBee_Sensor import XBee_Sensor, SensorClosedError

class XBee_Sensor_Physical(XBee_Sensor):
    def __init__(self, arguments, thread_manager, usb_manager,
                 location_callback, receive_callback, valid_callback):
        """
        Initialize the physical XBee sensor.
        """

        self._type = "xbee_sensor_physical"

        super(XBee_Sensor_Physical, self).__init__(arguments, thread_manager, usb_manager,
                                                   location_callback, receive_callback, valid_callback)

        self._serial_connection = None
        self._node_identifier_set = False
        self._address_set = False
        self._synchronized = False
        self._discovery_callback = None
        self._ntp = NTP(self)
        self._ntp_delay = self._settings.get("ntp_delay")

        # Prepare the packet and sensor data.
        self._sensors = self._settings.get("sensors")
        for index, address in enumerate(self._sensors):
            self._sensors[index] = address.decode("string_escape")

    def setup(self):
        """
        Setup the serial connection and identify the sensor.
        """

        port = self._settings.get("port")
        if port != "":
            self._serial_connection = self._usb_manager.get_xbee_device(port)
        else:
            self._serial_connection = self._usb_manager.get_xbee_device()

        self._sensor = ZigBee(self._serial_connection, callback=self._receive,
                              error_callback=self._error)
        time.sleep(self._settings.get("startup_delay"))

        self._identify()

    def activate(self):
        """
        Activate the sensor to send and receive packets.
        """

        super(XBee_Sensor_Physical, self).activate()

        if not self._active:
            self._active = True

            if self._serial_connection is None:
                self.setup()

            self._join()
            thread.start_new_thread(self._loop, ())

    def _loop(self):
        """
        Execute the sensor loop. This runs in a separate thread.
        """

        try:
            while self._active:
                # Ensure that the sensor has joined the network.
                if not self._joined:
                    time.sleep(self._loop_delay)
                    continue

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
        except SensorClosedError:
            # Serial connection was removed by deactivate, so end the loop.
            pass
        except:
            super(XBee_Sensor_Physical, self).interrupt()

    def deactivate(self):
        """
        Deactivate the sensor and close the serial connection.
        """

        super(XBee_Sensor_Physical, self).deactivate()

        if self._active or self._serial_connection is not None:
            self._active = False

            if self._serial_connection is not None:
                # Halt the internal xbee library thread to ensure that this 
                # unregistered thread is also stopped.
                # Only do so when the thread is still alive. For example, in 
                # tests the connection may be started but not the thread. Then 
                # the halt method may raise an exception about joining a thread 
                # before it is started.
                if self._sensor.is_alive():
                    self._sensor.halt()

                self._serial_connection = None

    def discover(self, callback):
        """
        Discover other XBee devices in the network.

        This method is only used on the ground station in the control panel
        to refresh the status of the other XBee devices.
        """

        if not hasattr(callback, "__call__"):
            raise TypeError("Discovery callback is not callable")

        self._discovery_callback = callback
        self._sensor.send("at", command="ND")

    def _identify(self):
        """
        Identify the sensor by fetching its node identifier and address.
        """

        response_delay = self._settings.get("response_delay")

        while not self._node_identifier_set:
            self._sensor.send("at", command="NI")
            time.sleep(response_delay)

        while not self._address_set:
            self._sensor.send("at", command="SH")
            time.sleep(response_delay)
            self._sensor.send("at", command="SL")
            time.sleep(response_delay)

    def _join(self):
        """
        Join the network and synchronize the clock if necessary.
        """

        response_delay = self._settings.get("response_delay")

        while not self._joined:
            self._sensor.send("at", command="AI")
            time.sleep(response_delay)

        if self._id > 0 and self._settings.get("synchronize"):
            # Synchronize the clock with the ground station's clock before
            # sending messages. This avoids clock skew caused by the fact that
            # the Raspberry Pi devices do not have an onboard real time clock.
            while not self._synchronized:
                self._ntp.start()
                time.sleep(self._ntp_delay)

    def _send(self):
        """
        Send a packet to each other sensor in the network.
        """

        # Create and send the RSSI broadcast packets.
        packet = self._make_rssi_broadcast_packet()

        for index in xrange(1, self._number_of_sensors + 1):
            if index == self._id:
                continue

            self._send_tx_frame(packet, index)

        # Send the sweep data to the ground sensor and clear the list
        # for the next round.
        for frame_id in self._data.keys():
            packet = self._data[frame_id]
            if packet.get("rssi") is None:
                continue

            self._send_tx_frame(packet, 0)
            self._data.pop(frame_id)

    def _send_tx_frame(self, packet, to=None):
        """
        Send a TX frame to another sensor.
        """

        super(XBee_Sensor_Physical, self)._send_tx_frame(packet, to)

        if self._serial_connection is None:
            raise SensorClosedError

        self._sensor.send("tx", dest_addr_long=self._sensors[to], dest_addr="\xFF\xFE",
                          frame_id="\x00", data=packet.serialize())

    def _error(self, e):
        """
        Handle an exception within the XBee sensor thread.
        """

        super(XBee_Sensor_Physical, self).interrupt()

    def _receive(self, raw_packet):
        """
        Receive and process a raw packet from another sensor in the network.
        """

        if raw_packet["id"] == "rx":
            self._process_rx(raw_packet)
        elif raw_packet["id"] == "at_response":
            self._process_at_response(raw_packet)

    def _process_rx(self, raw_packet):
        """
        Process RX packets and handle NTP and RSSI requests.
        """

        # Convert the raw packet to a `Packet` object according to specifications.
        packet = Packet()
        packet.unserialize(raw_packet["rf_data"])

        # Check whether the packet is not private and pass it along to the 
        # receive callback.
        if self._check_receive(packet):
            return

        # Handle NTP synchronization packets.
        if packet.get("specification") == "ntp":
            self._ntp.process(packet)
            return

        # Handle an RSSI ground station packet.
        if self._id == 0:
            if self._buffer is not None:
                self._buffer.put(packet)

            return

        # Handle a received RSSI broadcast packet.
        self._process_rssi_broadcast_packet(packet)

    def _process_rssi_broadcast_packet(self, packet):
        """
        Process a received packet with RSSI measurements.
        """

        # Synchronize the scheduler using the timestamp in the packet.
        self._next_timestamp = self._scheduler.synchronize(packet)

        # Create the packet for the ground station.
        ground_station_packet = self._make_rssi_ground_station_packet(packet)

        # Generate a frame ID to be able to match this packet and the
        # associated RSSI (DB command) request.
        frame_id = chr(random.randint(1, 255))
        self._data[frame_id] = ground_station_packet

        # Request the RSSI value for the received packet.
        self._sensor.send("at", command="DB", frame_id=frame_id)

    def _process_at_response(self, raw_packet):
        """
        Process AT response packets, for example for setting the node
        identifier and getting the RSSI value.
        """

        if raw_packet["command"] == "DB":
            # RSSI value has been received. Update the original packet.
            if raw_packet["frame_id"] in self._data:
                original_packet = self._data[raw_packet["frame_id"]]
                original_packet.set("rssi", -ord(raw_packet["parameter"]))
        elif raw_packet["command"] == "SH":
            # Serial number (high) has been received.
            if self._address is None:
                self._address = raw_packet["parameter"]
            elif raw_packet["parameter"] not in self._address:
                self._address = raw_packet["parameter"] + self._address
                self._address_set = True
        elif raw_packet["command"] == "SL":
            # Serial number (low) has been received.
            if self._address is None:
                self._address = raw_packet["parameter"]
            elif raw_packet["parameter"] not in self._address:
                self._address = self._address + raw_packet["parameter"]
                self._address_set = True
        elif raw_packet["command"] == "NI":
            # Node identifier has been received.
            self._id = int(raw_packet["parameter"])
            self._scheduler.id = self._id
            self._node_identifier_set = True
        elif raw_packet["command"] == "AI":
            # Association indicator has been received.
            if raw_packet["parameter"] == "\x00":
                self._joined = True
        elif raw_packet["command"] == "ND":
            # Node discovery packet has been received.
            packet = raw_packet["parameter"]
            data = {
                "id": int(packet["node_identifier"]),
                "address": self._format_address(packet["source_addr_long"])
            }
            self._discovery_callback(data)

    def _format_address(self, address):
        """
        Pretty print a given address.
        """

        if address is None:
            return "-"

        address = "%02x:%02x:%02x:%02x:%02x:%02x:%02x:%02x" % struct.unpack("BBBBBBBB", address)
        return address.upper()
