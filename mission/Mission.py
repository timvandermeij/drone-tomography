import math
import sys
import time
from dronekit import LocationGlobal, VehicleMode
from ..trajectory.Memory_Map import Memory_Map
from ..geometry.Geometry_Spherical import Geometry_Spherical

class Mission(object):
    """
    Mission trajactory utilities.

    This includes generic methods to set up a mission and methods to check the
    state of the vehicle and handle actions during the mission.

    Actual missions are implemented as subclass of the `Mission_Guided` and
    `Mission_Auto` classes.
    """

    def __init__(self, environment, settings):
        self.environment = environment
        self.vehicle = self.environment.get_vehicle()

        self.geometry = self.environment.get_geometry()
        self.settings = settings
        self.memory_map = None

    @classmethod
    def create(cls, environment, arguments):
        """
        Create a `Mission` object from one of the mission subclass types.

        `arguments` is an Arguments object that Vehicle subclasses can use to
        deduce settings from.
        """

        settings = arguments.get_settings("mission")
        mission_class_name = settings.get("mission_class")

        import_manager = environment.get_import_manager()
        mission_class = import_manager.load_class(mission_class_name,
                                                  relative_module="mission")

        return mission_class(environment, settings)

    def distance_to_current_waypoint(self):
        """
        Gets distance in meters to the current waypoint.

        This method returns `None` for the first waypoint (Home location) or
        other non-waypoint commands (such as waiting indefinitely).
        """

        waypoint_location = self.vehicle.get_waypoint()
        if waypoint_location is None:
            return None

        distance = self.environment.get_distance(waypoint_location)
        return distance

    def setup(self):
        """
        Setup the mission by clearing any old missions, importing the mission
        settings, and setting up dependent objects.
        """

        # Clear the current mission
        self.clear_mission()

        # Size in meters of one dimension of the part of the space that we are 
        # allowed to be in.
        self.size = self.settings.get("space_size")
        # The number of entries in the memory map per meter
        self.resolution = self.settings.get("resolution")

        # The space around the vehicle's center (where the distance sensor is) 
        # that we do not want to have other objects in. This is used for 
        # additional padding in certain calculations.
        self.padding = self.settings.get("padding")

        # Operating altitude in meters
        self.altitude = self.settings.get("altitude")

        # Speed of the vehicle in meters per second when moving to a location 
        # given in a (goto) command.
        self.speed = self.settings.get("speed")

        # Margin in meters at which we are too close to an object
        self.closeness = self.settings.get("closeness")
        # Distance in meters above which we are uninterested in objects
        self.farness = self.settings.get("farness")

        # Whether to synchronize vehicles at waypoints
        self._rf_sensor_synchronization = self.settings.get("rf_sensor_synchronization")

        # Create a memory map for the vehicle to track where it has seen 
        # objects. This can later be used to find the target object or to fly 
        # around obstacles without colliding.
        # The size is the number of entries in each dimension. We add some 
        # padding to allow for deviations.
        memory_size = (self.size + self.padding)*2
        self.memory_map = Memory_Map(self.environment, memory_size, self.resolution, self.altitude)

    def display(self):
        """
        Display any details about the mission.
        """
        pass

    def clear_mission(self):
        """
        Clear the current mission.
        """

        print('Clearing mission and redownloading default mission...')
        self.vehicle.clear_waypoints()
        self.vehicle.update_mission()

    def check_mission(self):
        """
        Check the mission's commands and display useful data about them.

        We also extract the home location from the vehicle.
        """

        print("{} commands in the mission!".format(self.vehicle.count_waypoints()))

        home_location = self.vehicle.home_location
        if home_location is not None:
            print("Home location: {}".format(home_location))
            if isinstance(home_location, LocationGlobal) and isinstance(self.geometry, Geometry_Spherical):
                self.geometry.set_home_location(home_location)

    def get_waypoints(self):
        """
        Retrieve a list of waypoints in this mission.
        The waypoints are `Location` objects.

        The list may be cached, and may be different from waypoints that are
        currently stored in the vehicle.

        It is used by the AUTO missions to fill the mission commands.
        Other missions may use it for their own waypoin tracking purposes.
        """

        return []

    def get_home_location(self):
        """
        Return the home location object from the vehicle.
        """

        return self.vehicle.home_location

    def arm_and_takeoff(self):
        """
        Arms vehicle and fly to the target `altitude`.
        """
        print("Basic pre-arm checks")
        if not self.vehicle.check_arming():
            raise RuntimeError("Could not prepare for arming!")

        print("Arming motors")
        self.vehicle.armed = True

        while not self.vehicle.armed:
            print(" Waiting for arming...")
            time.sleep(1)

        # Take off to target altitude
        print("Taking off!")
        taking_off = self.vehicle.simple_takeoff(self.altitude)
        self.vehicle.speed = self.speed

        if not taking_off:
            return

        # Wait until the vehicle reaches a safe height before processing the 
        # goto (otherwise the command after Vehicle.commands.takeoff will 
        # execute immediately).
        # Allow it to fly to just below target, in case of undershoot.
        altitude_undershoot = self.settings.get("altitude_undershoot")
        alt = self.altitude * altitude_undershoot
        while self.vehicle.location.global_relative_frame.alt < alt:
            print("Altitude: {} m".format(self.vehicle.location.global_relative_frame.alt))
            time.sleep(1)

        print("Reached target altitude")

    def start(self):
        """
        Actually start the mission after arming and flying off.
        """

        raise NotImplementedError("Must be implemented in child class")

    def stop(self):
        """
        Stop the vehicle and end the mission immediately.
        """

        self.vehicle.armed = False

    def step(self):
        """
        Perform any calculations for the current vehicle state.
        """

        pass

    def check_sensor_distance(self, sensor_distance, yaw, pitch):
        """
        Decide on handling a measured `sensor_distance` to an object.
        If we are too close to an object, we should take action by stopping the
        vehicle. Some missions may be able to go somewhere else based on this
        information. The `RuntimeError` this raises may therefore be mitigated
        by the mission class or the caller, e.g., `Monitor` or the mission
        script.

        Returns `True` if the sensor distance is close enough to be relevant
        for the mission.
        """

        if sensor_distance == 0:
            print("Inside the object, abort mission.")
            sys.exit(1)
        elif sensor_distance <= self.closeness:
            self.vehicle.mode = VehicleMode("GUIDED")
            self.vehicle.speed = 0.0
            raise RuntimeError("Too close to the object ({} m), halting.".format(sensor_distance))
        elif sensor_distance < self.farness:
            return True

        return False

    def check_waypoint(self):
        """
        Handle waypoint locations in the mission.
        Only used when this is an AUTO mission.
        We can perform other tasks when we are close to the next waypoint.
        Returns `False` when there are no more commands in the mission.
        """

        return True

    def get_space_size(self):
        """
        Get the space size in meters for the current mission.
        """

        return self.size

    def get_memory_map(self):
        """
        Get the `Memory_Map` object.
        """

        return self.memory_map

    def send_global_velocity(self, velocity_x, velocity_y, velocity_z):
        """
        Move vehicle in direction based on specified velocity vectors.

        This should be used in GUIDED mode. See `vehicle.speed` that works in
        AUTO mode.
        """

        self.vehicle.velocity = [velocity_x, velocity_y, velocity_z]

    def _get_new_yaw(self, heading, relative):
        if relative:
            new_yaw = self.vehicle.attitude.yaw + heading * math.pi/180
        else:
            new_yaw = heading * math.pi/180

        return new_yaw

    def set_yaw(self, heading, relative=False, direction=0):
        """
        Set the bearing `heading` of the vehicle in degrees. The heading becomes
        the yaw of the vehicle (the direction in which it is facing).
        The `heading` is a bearing, meaning that north is zero degrees and
        values are increasing counterclockwise.

        This command works in GUIDED mode and may only work after a velocity
        command has been issued, depending on the vehicle autopilot.

        If `relative` is `False`, then `heading` is the number of degrees off
        from northward direction, increasing counterclockwise as usual.
        If `relative` is `True`, the `heading` is still given as a bearing, but
        is now respective to the vehicle's current yaw.

        The `direction` gives the direction in which we should rotate: `1` is
        clockwise and `-1` is counterclockwise. If `direction` is `0`, then use
        the direction in which we reach the requested `heading` the quickest.
        """

        if direction == 0:
            yaw = self.vehicle.attitude.yaw
            new_yaw = self._get_new_yaw(heading, relative)

            # -1 because the yaw is given as a bearing that increases clockwise 
            # while geometry works with angles that increase counterclockwise.
            direction = -1 * self.geometry.get_direction(yaw, new_yaw)

        self.vehicle.set_yaw(heading, relative, direction)

    def set_sensor_yaw(self, heading, relative=False, direction=0):
        """
        Set the yaw `heading` for the distance sensors.

        This may be accomplished by changing the yaw of the entire vehicle, or
        by changing a servo PWM output to turn the distance sensor to a certain
        angle. If vehicle angle changing is used, then the arguments `relative`
        and `direction` have the same meaning as in `set_yaw`.

        In either case, at least one of the distance sensors (if there are any)
        will in time point in the given direction.
        """

        if not self.environment.get_servos():
            self.set_yaw(heading, relative, direction)
            return

        new_yaw = self._get_new_yaw(heading, relative)
        yaw_angle = self.geometry.bearing_to_angle(new_yaw - self.vehicle.attitude.yaw) * 180/math.pi
        servo = None
        pwm = None
        for servo in self.environment.get_servos():
            if servo.check_value(yaw_angle):
                pwm = servo.get_pwm(yaw_angle)
                self.vehicle.set_servo(servo, pwm)
                return

        self.set_yaw(heading, relative, direction)

    def return_to_launch(self):
        """
        Set the vehicle in return-to-launch (RTL) mode, which depending on
        vehicle type causes it to return to its home location.

        Use only when ending a mission in a safe environment.
        """

        print("Return to launch")
        self.vehicle.mode = VehicleMode("RTL")
