# Core imports
import copy
import Queue
import thread
import time

# Package imports
from ..core.Threadable import Threadable
from ..reconstruction.Buffer import Buffer
from ..settings import Arguments
from Packet import Packet
from TDMA_Scheduler import TDMA_Scheduler

# pylint: disable=undefined-all-variable
__all__ = [
    "RF_Sensor_Simulator", "RF_Sensor_Physical_XBee",
    "RF_Sensor_Physical_Texas_Instruments"
]

class RSSI_Validity_Request(object):
    """
    A request to the valid location callback, containing properties that the
    valid location callback can use to track the measurement validity.
    """

    def __init__(self, specification, other_id=None, other_valid=None,
                 other_valid_pair=None, other_index=None):
        self._is_broadcast = specification == "rssi_broadcast"
        self._other_valid = other_valid
        self._other_id = other_id
        self._other_index = other_index
        self._other_valid_pair = other_valid_pair

    @property
    def is_broadcast(self):
        """
        Whether the RSSI packet is a measurement broadcast packet, or that it
        is sent to the ground station.
        """

        return self._is_broadcast

    @property
    def other_id(self):
        """
        RF sensor ID of the other sensor.
        """

        return self._other_id

    @property
    def other_valid(self):
        """
        Whether the location of the other sensor is valid.
        """

        return self._other_valid

    @property
    def other_valid_pair(self):
        """
        Whether the other sensor has received a valid measurement from the
        current sensor.
        """

        return self._other_valid_pair

    @property
    def other_index(self):
        """
        The waypoint index of the other sensor.
        """

        return self._other_index

class DisabledException(Exception):
    """
    Special exception indicating that the RF sensor was disabled during
    execution of the sensor loop.
    """

    pass 

class RF_Sensor(Threadable):
    """
    Base class for all RF sensors.

    This class is responsible for setting up the basic characteristics of an
    RF sensor and contains common code for the simulated and physical
    specializations.
    """

    def __init__(self, arguments, thread_manager, location_callback,
                 receive_callback, valid_callback):
        """
        Initialize the RF sensor.

        The `arguments` parameter is used to load settings for a specific RF
        sensor type. The sensor has a `thread_manager`, which is a `Thread_Manager`
        object for registering its own thread loop. Additionally, it requires
        certian callbacks. The `location_callback` is called whenever the sensor
        needs to know its own location for the "rssi_broadcast" and the
        "rssi_ground_station" private packets. The `receive_callback` is called
        whenever non-private packets are received and has the `Packet` object
        as an argument. Finally, the `valid_callback` is called shortly after
        the `location_callback` is called. It may be given a boolean argument
        indicating whether another RF sensor has a valid location, but only when
        creating the "rssi_ground_station" private packet. This is used by the
        callback to determine if measurements at a certain location are finished.

        Classes that inherit this base class may extend this method.
        """

        super(RF_Sensor, self).__init__("rf_sensor", thread_manager)

        # Make sure that the provided callbacks are callable.
        for callback in [location_callback, receive_callback, valid_callback]:
            if not hasattr(callback, "__call__"):
                raise TypeError("Provided RF sensor callback is not callable")

        # Load settings for a specific RF sensor type.
        if isinstance(arguments, Arguments):
            self._settings = arguments.get_settings(self.type)
        else:
            raise ValueError("'arguments' must be an instance of Arguments")

        # Initialize common member variables.
        self._id = self._settings.get("rf_sensor_id")
        self._number_of_sensors = self._settings.get("number_of_sensors")
        self._address = None
        self._connection = None
        self._buffer = None
        self._scheduler = TDMA_Scheduler(self._id, arguments)
        self._packets = Queue.Queue()
        self._custom_packets = Queue.Queue()

        self._joined = False
        self._activated = False
        self._started = False

        self._loop_delay = self._settings.get("loop_delay")

        self._location_callback = location_callback
        self._receive_callback = receive_callback
        self._valid_callback = valid_callback

    @property
    def id(self):
        """
        Get the ID of the RF sensor.
        """

        return self._id

    @property
    def number_of_sensors(self):
        """
        Get the number of sensors in the network.
        """

        return self._number_of_sensors

    @property
    def buffer(self):
        """
        Get the buffer of the RF sensor.
        """

        return self._buffer

    @buffer.setter
    def buffer(self, buffer):
        """
        Set the buffer.

        The `buffer` argument must be a `Buffer` object.
        """

        if not isinstance(buffer, Buffer):
            raise ValueError("The `buffer` argument must be a `Buffer` object")

        self._buffer = buffer

    @property
    def type(self):
        raise NotImplementedError("Subclasses must implement the `type` property")

    @property
    def identity(self):
        """
        Get the identity of the RF sensor, consisting of its ID, address and
        network join status.

        Classes that inherit this base class may extend this property.
        """

        return {
            "id": self._id,
            "address": self._address,
            "joined": self._joined
        }

    def activate(self):
        """
        Activate the sensor to start sending and receiving packets.

        Classes that inherit this base class may extend this method.
        """

        super(RF_Sensor, self).activate()

        if not self._activated:
            self._activated = True

            if self._connection is None:
                self._setup()

            thread.start_new_thread(self._loop, ())

    def deactivate(self):
        """
        Deactivate the sensor to stop sending and receiving packets.

        Classes that inherit this base class may extend this method.
        """

        super(RF_Sensor, self).deactivate()

        if self._activated:
            self._activated = False

        if self._connection is not None:
            # Close the connection and clean up so that the thread might get 
            # the signal faster and we can correctly reactivate later on.
            self._connection.close()
            self._connection = None

    def start(self):
        """
        Start the signal strength measurements (and stop sending custom packets).

        Classes that inherit this base class may extend this method.
        """

        self._scheduler.update()
        self._packets = Queue.Queue()
        self._started = True

    def stop(self):
        """
        Stop the signal strength measurements (and start sending custom packets).
        """

        self._started = False

        # Reset the scheduler timestamp so that it updates correctly in case we 
        # restart the sensor measurements.
        self._scheduler.timestamp = 0

    def enqueue(self, packet, to=None):
        """
        Enqueue a custom `packet` to send `to` another RF sensor in the network.
        """

        if not isinstance(packet, Packet):
            raise TypeError("Only `Packet` objects can be enqueued")

        if packet.is_private():
            raise ValueError("Private packets cannot be enqueued")

        if to is None:
            # No destination ID has been provided, so we broadcast the packet to
            # all sensors in the network except for ourself and the ground station.
            for to_id in xrange(1, self._number_of_sensors + 1):
                if to_id == self._id:
                    continue

                self._custom_packets.put({
                    "packet": copy.deepcopy(packet),
                    "to": to_id
                })
        else:
            self._custom_packets.put({
                "packet": packet,
                "to": to
            })

    def discover(self, callback, required_sensors=None):
        """
        Discover RF sensors in the network. The `callback` callable function is
        called when an RF sensor reports its identity. The `required_sensors`
        set indicates which sensors should be discovered; if it is not
        provided, then all RF sensors are discovered. Note that discovery may
        fail due to interference or disabled sensors.

        Classes that inherit this base class must extend this method.
        """

        if not hasattr(callback, "__call__"):
            raise TypeError("Provided discovery callback is not callable")

        if isinstance(required_sensors, set):
            if not required_sensors.issubset(range(1, self._number_of_sensors + 1)):
                raise ValueError("Provided required sensors may only contain vehicle sensors")
        elif required_sensors is not None:
            raise TypeError("Provided required sensors must be a `set`")

    def _setup(self):
        raise NotImplementedError("Subclasses must implement `_setup()`")

    def _loop(self):
        """
        Execute the sensor loop. This runs in a separate thread.
        """

        try:
            while self._activated:
                self._loop_body()
        except DisabledException:
            return
        except:
            super(RF_Sensor, self).interrupt()

    def _loop_body(self):
        """
        Body of the sensor loop.

        This is extracted into a separate method to make testing easier, as well
        as for keeping the `_loop` implementation in the base class.

        Classes that inherit this base class must extend this method.
        """

        # If the sensor has been activated, we only send enqueued custom packets.
        # If the sensor has been started, we stop sending custom packets and
        # start performing signal strength measurements.
        if not self._started:
            self._send_custom_packets()
        elif self._id > 0 and self._scheduler.in_slot:
            self._send()
            self._scheduler.update()

        time.sleep(self._loop_delay)

    def _send(self):
        """
        Send a broadcast packet to each other sensor in the network and
        send collected packets to the ground station.

        Classes that inherit this base class may extend this method.
        """

        # Create and send the RSSI broadcast packets.
        for to_id in xrange(1, self._number_of_sensors + 1):
            if not self._scheduler.in_slot:
                return

            if to_id == self._id:
                continue

            packet = self._create_rssi_broadcast_packet(to_id)
            self._send_tx_frame(packet, to_id)

        # Send collected packets to the ground station.
        while not self._packets.empty() and self._scheduler.in_slot:
            packet = self._packets.get()
            self._send_tx_frame(packet, 0)

    def _send_custom_packets(self):
        """
        Send custom packets to their destinations.
        """

        while not self._custom_packets.empty():
            item = self._custom_packets.get()
            self._send_tx_frame(item["packet"], item["to"])

    def _send_tx_frame(self, packet, to=None):
        """
        Send a TX frame with `packet` as payload `to` another sensor.

        Classes that inherit this base class must extend this method.
        """

        if self._connection is None:
            raise DisabledException

        if not isinstance(packet, Packet):
            raise TypeError("Only `Packet` objects can be sent")

        if to is None:
            raise TypeError("Invalid destination '{}' has been provided".format(to))

        # Introduce a short delay to give the hardware more time to send
        # packets when this method is called many times in a row.
        time.sleep(self._loop_delay)

    def _receive(self, packet=None):
        raise NotImplementedError("Subclasses must implement `_receive(packet=None)`")

    def _create_rssi_broadcast_packet(self, to_id):
        """
        Create a `Packet` object according to the "rssi_broadcast" specification.
        The resulting packet is complete.
        """

        location, waypoint_index = self._location_callback()
        request = RSSI_Validity_Request("rssi_broadcast", other_id=to_id)
        valid, valid_pair = self._valid_callback(request)

        packet = Packet()
        packet.set("specification", "rssi_broadcast")
        packet.set("latitude", location[0])
        packet.set("longitude", location[1])
        packet.set("valid", valid)
        packet.set("valid_pair", valid_pair)
        packet.set("waypoint_index", waypoint_index)
        packet.set("sensor_id", self._id)
        packet.set("timestamp", time.time())

        return packet

    def _create_rssi_ground_station_packet(self, rssi_broadcast_packet):
        """
        Create a `Packet` object according to the "rssi_ground_station"
        specification using data from an `rssi_broadcast_packet`. The
        `rssi_broadcast_packet` must be created according to the
        "rssi_broadcast" specification.

        The resulting packet is only missing RSSI information.

        The packet can be sent to the ground station as an indication of the
        signal strength between the RF sensor that sent the `rssi_broadcast_packet`
        and the current RF sensor.
        """

        from_valid = rssi_broadcast_packet.get("valid")
        from_id = rssi_broadcast_packet.get("sensor_id")
        from_waypoint_index = rssi_broadcast_packet.get("waypoint_index")
        from_valid_pair = rssi_broadcast_packet.get("valid_pair")

        location = self._location_callback()[0]
        request = RSSI_Validity_Request("rssi_ground_station", other_id=from_id,
                                        other_valid=from_valid,
                                        other_valid_pair=from_valid_pair,
                                        other_index=from_waypoint_index)
        to_valid = self._valid_callback(request)[0]

        packet = Packet()
        packet.set("specification", "rssi_ground_station")
        packet.set("sensor_id", self._id)
        packet.set("from_latitude", rssi_broadcast_packet.get("latitude"))
        packet.set("from_longitude", rssi_broadcast_packet.get("longitude"))
        packet.set("from_valid", from_valid)
        packet.set("to_latitude", location[0])
        packet.set("to_longitude", location[1])
        packet.set("to_valid", to_valid)

        return packet
