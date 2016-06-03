import time
from dronekit import LocationGlobalRelative
from Mission_Auto import Mission_Auto
from ..zigbee.XBee_Packet import XBee_Packet

class Mission_XBee(Mission_Auto):
    def setup(self):
        super(Mission_XBee, self).setup()
        self.environment.add_packet_action("waypoint_clear", self._clear_waypoints)
        self.environment.add_packet_action("waypoint_add", self._add_waypoint)
        self.environment.add_packet_action("waypoint_done", self._complete_waypoints)

        self._waypoints_complete = False
        self._next_index = 0

    def arm_and_takeoff(self):
        # Wait until all the waypoints have been received before arming.
        while not self._waypoints_complete:
            time.sleep(1)

        super(Mission_XBee, self).arm_and_takeoff()

    def _complete_waypoints(self, packet):
        xbee_sensor = self.environment.get_xbee_sensor()
        if xbee_sensor.id != packet.get("to_id"):
            # Ignore packets not meant for us.
            return

        print('Waypoints complete!')

        self._waypoints_complete = True

    @property
    def waypoints_complete(self):
        """
        Accessor for whether all the waypoints have been received.
        """

        return self._waypoints_complete

    @property
    def next_index(self):
        """
        Accessor for the next waypoint index that should be received from the
        ground station.
        """

        return self._next_index

    def get_points(self):
        # We do not have points for commands that are automatically added, 
        # because we add them when they arrive.
        return []

    def add_commands(self):
        # Commands are added when they arrive, not in here.
        pass

    def _send_ack(self):
        """
        Send a "waypoint_ack" packet to the ground station.

        This packet mentions which waypoint index we expect next, which is 0
        when we do not have any waypoints anymore or the next unused index
        otherwise.
        """

        xbee_sensor = self.environment.get_xbee_sensor()

        ack_packet = XBee_Packet()
        ack_packet.set("specification", "waypoint_ack")
        ack_packet.set("next_index", self._next_index)
        ack_packet.set("sensor_id", xbee_sensor.id)

        xbee_sensor.enqueue(ack_packet, to=0)

    def _clear_waypoints(self, packet):
        """
        Clear the mission waypoints after receiving a "waypoint_clear" packet.
        """

        xbee_sensor = self.environment.get_xbee_sensor()
        if xbee_sensor.id != packet.get("to_id"):
            # Ignore packets not meant for us.
            return

        self.clear_mission()
        # Add a takeoff command for flying vehicles that use it.
        self.add_takeoff()
        self._next_index = 0
        self._send_ack()

    def _add_waypoint(self, packet):
        """
        Add a waypoint to the mission based on a "waypoint_add" packet.

        The packet must have the XBee sensor ID in the "to_id" field and the
        index must be the next waypoint index; otherwise, the waypoint is not
        added to the vehicle's waypoints.
        """

        xbee_sensor = self.environment.get_xbee_sensor()
        if xbee_sensor.id != packet.get("to_id"):
            # Ignore packets not meant for us.
            return

        index = packet.get("index")
        if index != self._next_index:
            # Send a reply saying what index were are currently at and ignore 
            # the packet, which may be duplicate or out of order.
            self._send_ack()
            return

        latitude = packet.get("latitude")
        longitude = packet.get("longitude")
        altitude = packet.get("altitude")
        wait_id = packet.get("wait_id")

        # Make a location waypoint. `add_waypoint` handles any further 
        # conversion steps.
        point = LocationGlobalRelative(latitude, longitude, altitude)
        required_sensors = [wait_id] if wait_id > 0 else None
        self.add_waypoint(point, required_sensors)
        self._next_index += 1
        self._send_ack()
