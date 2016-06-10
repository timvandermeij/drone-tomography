import copy
import Queue
import time
from ..core.Threadable import Threadable
from ..reconstruction.Buffer import Buffer
from ..settings import Arguments
from Packet import Packet
from TDMA_Scheduler import TDMA_Scheduler

# pylint: disable=undefined-all-variable
__all__ = [
    "XBee_CC2530_Sensor_Physical", "XBee_Sensor_Physical", "XBee_Sensor_Simulator"
]

class SensorClosedError(Exception):
    """
    A special exception indicating that the sensor was disabled by deactivate
    during the execution of the sensor loop.
    """

    pass 

class XBee_Sensor(Threadable):
    """
    Base XBee sensor class.

    This class sets up some private characteristics of the XBee sensor handler,
    and contains common code for the simulated and physical specializations.
    """

    def __init__(self, arguments, thread_manager, usb_manager, location_callback,
                 receive_callback, valid_callback):
        """
        Set up the XBee sensor.

        The sensor has a `thread_manager`, which is a `Thread_Manager` object
        in which it can register its own thread loop. The physical XBee sensor
        uses a `usb_manager`, which we ignore for the simulator .Additionally, it
        requires certian callbacks. The `location_callback` is called whenever the
        XBee needs to know its own location for the "rssi_broadcast" and the
        "rssi_ground_station" private packets. The `receive_callback` is called
        whenever any non-private packets are received and has the `Packet`
        as an argument. Finally, the `valid_callback` is called shortly after
        the `location_callback` is called, and may be given a boolean argument
        indicating whether another XBee sensor has a valid location, but only
        when creating the "rssi_ground_station" private packet. This may be
        used by the callback to determine whether measurements at a certain
        location are finished.
        """

        super(XBee_Sensor, self).__init__("xbee_sensor", thread_manager)

        if not hasattr(location_callback, "__call__"):
            raise TypeError("Location callback is not callable")

        if not hasattr(receive_callback, "__call__"):
            raise TypeError("Receive callback is not callable")

        if not hasattr(valid_callback, "__call__"):
            raise TypeError("Valid location callback is not callable")

        if isinstance(arguments, Arguments):
            self._settings = arguments.get_settings(self._type)
        else:
            raise ValueError("'arguments' must be an instance of Arguments")

        self._sensor = None
        self._id = self._settings.get("rf_sensor_id")
        self._number_of_sensors = self._settings.get("number_of_sensors")
        self._buffer = None
        self._address = None
        self._next_timestamp = 0
        self._scheduler = TDMA_Scheduler(self._id, arguments)
        self._data = {}
        self._queue = Queue.Queue()
        self._loop_delay = self._settings.get("loop_delay")
        self._custom_packet_delay = self._settings.get("custom_packet_delay")
        self._active = False
        self._joined = False
        self._started = False

        self._usb_manager = usb_manager
        self._location_callback = location_callback
        self._receive_callback = receive_callback
        self._valid_callback = valid_callback

    @property
    def id(self):
        return self._id

    @property
    def number_of_sensors(self):
        return self._number_of_sensors

    def set_buffer(self, buffer):
        if not isinstance(buffer, Buffer):
            raise ValueError("The buffer object must be an instance of Buffer")

        self._buffer = buffer

    def get_identity(self):
        """
        Get the identity (ID, address and join status) of this sensor.
        """

        identity = {
            "id": self._id,
            "address": self._format_address(self._address),
            "joined": self._joined
        }
        return identity

    def setup(self):
        raise NotImplementedError("Subclasses must implement `setup()`")

    def start(self):
        """
        Start the signal strength measurements (and no longer send custom packets).
        """

        self._started = True

    def stop(self):
        """
        Stop the signal strength measurements (and send custom packets).
        """

        self._started = False

    def _loop(self):
        raise NotImplementedError("Subclasses must implement `_loop()`")

    def enqueue(self, packet, to=None):
        """
        Enqueue a custom packet to send to another XBee device.
        """

        if not isinstance(packet, Packet):
            raise TypeError("Only `Packet` objects can be enqueued")

        if packet.is_private():
            raise ValueError("Private packets cannot be enqueued")

        if to != None:
            self._queue.put({
                "packet": packet,
                "to": to
            })
        else:
            # No destination ID has been provided, therefore we broadcast
            # the packet to all sensors in the network except for ourself
            # and the ground sensor.
            for to_id in xrange(1, self._number_of_sensors + 1):
                if to_id == self._id:
                    continue

                self._queue.put({
                    "packet": copy.deepcopy(packet),
                    "to": to_id
                })

    def discover(self, callback):
        raise NotImplementedError("Subclasses must implement `discover(callback)`")

    def _send(self):
        raise NotImplementedError("Subclasses must implement `_send()`")

    def _send_custom_packets(self):
        """
        Send custom packets to their destinations.
        """

        while not self._queue.empty():
            item = self._queue.get()
            self._send_tx_frame(item["packet"], item["to"])

    def _send_tx_frame(self, packet, to=None):
        """
        Send a TX frame to another sensor.
        """

        if not isinstance(packet, Packet):
            raise ValueError("Invalid packet specified")

        if to is None:
            raise ValueError("Invalid destination specified: {}".format(to))

    def _receive(self, packet):
        raise NotImplementedError("Subclasses must implement `_receive(packet)`")

    def _format_address(self, address):
        raise NotImplementedError("Subclasses must implement `_format_address(address)`")

    def _check_receive(self, packet):
        """
        Check whether the given `packet` should be given to the receive callback
        rather than handling it internally.

        The return value is `False` if the packet should be handled internally,
        otherwise it is `True` and the calling method should stop handling it.
        """

        if not packet.is_private():
            self._receive_callback(packet)
            return True

        return False

    def _make_rssi_broadcast_packet(self):
        """
        Create a `Packet` object containing current location data.

        The packet is complete, including location validity, the sensor ID
        and the current timestamp.
        """

        location, waypoint_index = self._location_callback()

        packet = Packet()
        packet.set("specification", "rssi_broadcast")
        packet.set("latitude", location[0])
        packet.set("longitude", location[1])
        packet.set("valid", self._valid_callback())
        packet.set("waypoint_index", waypoint_index)
        packet.set("sensor_id", self._id)
        packet.set("timestamp", time.time())

        return packet

    def _make_rssi_ground_station_packet(self, rssi_packet):
        """
        Create a `Packet` object containing location data of the current
        XBee and data from an `rssi_packet`. The `rssi_packet` must have
        an "rssi_broadcast" specification.

        The resulting packet is only missing RSSI information.

        The packet can then be sent to the ground station as an indication of
        the signal strength between the XBee that sent the `rssi_packet` and
        the current XBee.
        """

        from_valid = rssi_packet.get("valid")
        from_id = rssi_packet.get("sensor_id")
        from_waypoint_index = rssi_packet.get("waypoint_index")

        location = self._location_callback()[0]
        location_valid = self._valid_callback(other_valid=from_valid,
                                              other_id=from_id,
                                              other_index=from_waypoint_index)

        ground_station_packet = Packet()
        ground_station_packet.set("specification", "rssi_ground_station")
        ground_station_packet.set("sensor_id", self._id)
        ground_station_packet.set("from_latitude", rssi_packet.get("latitude"))
        ground_station_packet.set("from_longitude", rssi_packet.get("longitude"))
        ground_station_packet.set("from_valid", from_valid)
        ground_station_packet.set("to_latitude", location[0])
        ground_station_packet.set("to_longitude", location[1])
        ground_station_packet.set("to_valid", location_valid)

        return ground_station_packet
