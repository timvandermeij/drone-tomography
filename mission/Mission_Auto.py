import time
from dronekit import LocationLocal, LocationGlobalRelative, VehicleMode
from Mission import Mission
from ..geometry.Geometry_Spherical import Geometry_Spherical

class Mission_Auto(Mission):
    """
    A mission that uses the AUTO mode to move to fixed locations.
    """

    def setup(self):
        super(Mission_Auto, self).setup()
        self._waypoints = None
        # Number of waypoints to skip in the commands list; the index of the 
        # first waypoint of our mission. For non-Rover vehicles, we add 
        # a takeoff command to the list that we need not display.
        self._first_waypoint = 1
        self._required_waypoint_sensors = []

    def arm_and_takeoff(self):
        self.add_commands()
        super(Mission_Auto, self).arm_and_takeoff()

    def get_waypoints(self):
        if self._waypoints is None:
            self._waypoints = self.get_points()

        return self._waypoints

    def get_points(self):
        """
        Retrieve a list of waypoint locations for this mission.

        This list is cached by `get_waypoints`.
        """

        raise NotImplementedError("Must be implemented in child class")

    def add_takeoff(self):
        """
        Add takeoff command. The command is ignored if the vehicle is already
        in the air, or if the vehicle is a ground vehicle. In this case, the
        command may even be not added at all, and the altitude is set to zero.
        """

        has_takeoff = self.vehicle.add_takeoff(self.altitude)
        if not has_takeoff:
            self.altitude = 0.0
            self._first_waypoint = 0

    def _convert_waypoint(self, point):
        """
        Convert a waypoint location object `point` to adhere to the current
        geometry's location and mission's operating altitude.
        """

        # Handle local locations, points without a specific altitude and 
        # non-spherical geometries.
        if isinstance(point, LocationLocal):
            down = point.down if point.down != 0.0 else -self.altitude
            return LocationLocal(point.north, point.east, down)

        alt = point.alt if point.alt != 0.0 else self.altitude
        if isinstance(self.geometry, Geometry_Spherical):
            return LocationGlobalRelative(point.lat, point.lon, alt)

        return LocationLocal(point.lat, point.lon, -alt)

    def add_waypoint(self, point, required_sensors=None):
        """
        Add a waypoint location object `point` to the vehicle's mission command
        waypoints.

        If RF sensor synchronization is enabled, also adds a wait command afterward.
        The option `required_sensors` list determines which sensors ID to wait
        for in the measurement validation.
        """

        self.vehicle.add_waypoint(self._convert_waypoint(point))

        if self._rf_sensor_synchronization:
            self.vehicle.add_wait()
            self._required_waypoint_sensors.append(required_sensors)

    def add_commands(self):
        """
        Adds a takeoff command and the waypoints to the current mission. 

        The function assumes that the vehicle waypoints are cleared and that we
        can now add the mission waypoints to the vehicle.
        """

        self.add_takeoff()

        # Add the waypoint commands.
        points = self.get_waypoints()
        for point in points:
            self.add_waypoint(point)

        # Send commands to vehicle and update.
        self.vehicle.update_mission()
        self.check_mission()

    def display(self):
        # Make sure that mission being sent is displayed on console cleanly
        time.sleep(self.settings.get("mission_delay"))
        self.check_mission()

    def start(self):
        # Set mode to AUTO to start mission
        self.vehicle.mode = VehicleMode("AUTO")

    def check_waypoint(self):
        if self.vehicle.is_wait():
            if self._rf_sensor_synchronization and self.environment.is_measurement_valid():
                # The vehicle is waiting for measurements to become valid, and 
                # they have, so go to the next waypoint. We do not need to give 
                # an explicit waypoint here since the vehicle never changes the 
                # waypoint in between here anyway.
                time.sleep(self.settings.get("measurement_delay"))
                print("Measurements are valid, continuing to next waypoint")
                self.vehicle.set_next_waypoint()
                index = self.vehicle.get_next_waypoint() / 2
                if index < len(self._required_waypoint_sensors):
                    required_sensors = self._required_waypoint_sensors[index]
                else:
                    required_sensors = None

                self.environment.invalidate_measurement(required_sensors)
            else:
                return True

        next_waypoint = self.vehicle.get_next_waypoint()
        distance = self.distance_to_current_waypoint()
        if distance is None:
            print('No distance to waypoint known!')
            return True

        if next_waypoint >= self._first_waypoint:
            if distance < self.farness:
                print("Distance to waypoint ({}): {} m".format(next_waypoint, distance))
                if distance <= self.closeness:
                    # We are close enough to the waypoint, so skip to the next 
                    # one so that we vehicle can prepare itself for that. We 
                    # pass an explicit waypoint number to avoid race conditions 
                    # with the vehicle's AUTO mode changing it in the meantime.
                    print("Close enough: skip to next waypoint")
                    self.vehicle.set_next_waypoint(next_waypoint + 1)
                    next_waypoint += 1

        return next_waypoint < self.vehicle.count_waypoints()
