import sys
import time
import math

import numpy as np

from droneapi.lib import VehicleMode, Location, Command
from pymavlink import mavutil

from ..geometry.Geometry import Geometry_Spherical
from Memory_Map import Memory_Map
from MockVehicle import MockVehicle

class Mission(object):
    """
    Mission trajactory utilities.
    This includes generic methods to set up a mission and methods to check and handle actions during the mission.
    Actual missions should be implemented as a subclass.
    """

    def __init__(self, api, environment, settings):
        self.api = api
        self.environment = environment
        self.vehicle = self.environment.get_vehicle()
        self.is_mock = False
        if isinstance(self.vehicle, MockVehicle):
            self.is_mock = True

        self.geometry = self.environment.get_geometry()
        self.settings = settings
        self.memory_map = None

    def distance_to_current_waypoint(self):
        """
        Gets distance in meters to the current waypoint. 
        It returns `None` for the first waypoint (Home location).
        """
        next_waypoint = self.vehicle.commands.next
        if next_waypoint <= 1:
            return None
        mission_item = self.vehicle.commands[next_waypoint]
        lat = mission_item.x
        lon = mission_item.y
        alt = mission_item.z
        waypoint_location = Location(lat, lon, alt, is_relative=True)
        distance = self.environment.get_distance(waypoint_location)
        return distance

    def setup(self):
        # Clear the current mission
        self.clear_mission()

        self.size = self.settings.get("size")
        self.altitude = self.settings.get("altitude")
        self.speed = self.settings.get("speed")

        # Margin in meters at which we are too close to an object
        self.closeness = self.settings.get("closeness")
        # Distance in meters above which we are uninterested in objects
        self.farness = self.settings.get("farness")

        # Create a memory map for the vehicle to track where it has seen 
        # objects. This can later be used to find the target object or to fly 
        # around obstacles without colliding.
        memory_size = self.get_space_size()
        self.memory_map = Memory_Map(self.environment, memory_size)

    def display(self):
        """
        Display any details about the mission.
        """
        pass

    def clear_mission(self):
        """
        Clear the current mission.
        """
        cmds = self.vehicle.commands
        self.vehicle.commands.clear()
        self.vehicle.flush()

        # After clearing the mission, we MUST re-download the mission from the 
        # vehicle before vehicle.commands can be used again.
        # See https://github.com/dronekit/dronekit-python/issues/230 for 
        # reasoning.
        self.download_mission()

    def download_mission(self):
        """
        Download the current mission from the vehicle.
        """
        cmds = self.vehicle.commands
        cmds.download()
        # Wait until download is complete.
        cmds.wait_valid()

    def get_commands(self):
        return self.vehicle.commands

    def arm_and_takeoff(self):
        """
        Arms vehicle and fly to the target `altitude`.
        """
        print("Basic pre-arm checks")
        # Don't let the user try to fly autopilot is booting
        while self.vehicle.mode.name == "INITIALISING":
            print("Waiting for vehicle to initialise...")
            time.sleep(1)
        while self.vehicle.gps_0.fix_type < 2:
            print("Waiting for GPS...: {}".format(self.vehicle.gps_0.fix_type))
            time.sleep(1)

        print("Arming motors")
        # Copter should arm in GUIDED mode
        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.armed = True
        self.vehicle.flush()

        while not self.vehicle.armed and not self.api.exit:
            print(" Waiting for arming...")
            time.sleep(1)

        # Take off to target altitude
        print("Taking off!")
        self.vehicle.commands.takeoff(self.altitude)
        self.set_speed(self.speed)
        self.vehicle.flush()

        # Wait until the vehicle reaches a safe height before processing the 
        # goto (otherwise the command after Vehicle.commands.takeoff will 
        # execute immediately).
        altitude_undershoot = self.settings.get("altitude_undershoot")
        while not self.api.exit:
            print(" Altitude: {} m".format(self.vehicle.location.alt))
            # Just below target, in case of undershoot.
            if self.vehicle.location.alt >= self.altitude * altitude_undershoot:
                print("Reached target altitude")
                break
            time.sleep(1)

    def start(self):
        """
        Actually start the mission after arming and flying off.
        """
        raise NotImplemented("Must be implemented in child class")

    def step(self):
        """
        Perform any calculations for the current vehicle state.
        """
        pass

    def check_sensor_distance(self, sensor_distance, yaw, pitch):
        """
        Decide on doing something with the measured distance.
        If we're too close, we should take action by stopping and going somewhere else.
        Returns `True` if the sensor distance is close enough to be relevant for us.
        """
        if sensor_distance == 0:
            print("Inside the object, abort mission.")
            sys.exit(1)
        elif sensor_distance < self.closeness:
            self.vehicle.mode = VehicleMode("GUIDED")
            self.set_speed(0)
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
        return self.size * 4

    def get_memory_map(self):
        return self.memory_map

    def set_speed(self, speed):
        """
        Set the current speed of the vehicle during AUTO or GUIDED mode.
        """
        if self.is_mock:
            self.vehicle.speed = speed
            return

        msg = self.vehicle.message_factory.command_long_encode(
            0, 0,    # target system, target component
            mavutil.mavlink.MAV_CMD_DO_CHANGE_SPEED, # command
            0, # confirmation
            0, # param 1
            speed, # speed in meters/second
            0, 0, 0, 0, 0 # param 3 - 7
        )

        # Send command to vehicle
        self.vehicle.send_mavlink(msg)
        self.vehicle.flush()

    def send_global_velocity(self, velocity_x, velocity_y, velocity_z):
        """
        Move vehicle in direction based on specified velocity vectors.

        This should be used in GUIDED mode. See `set_speed` for another command that works in AUTO mode.
        """
        if self.is_mock:
            self.vehicle.velocity = [velocity_x, velocity_y, velocity_z]
            return

        msg = self.vehicle.message_factory.set_position_target_global_int_encode(
            0,       # time_boot_ms (not used)
            0, 0,    # target system, target component
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT, # frame
            0b0000111111000111, # type_mask (only speeds enabled)
            0, # lat_int - X Position in WGS84 frame in 1e7 * meters
            0, # lon_int - Y Position in WGS84 frame in 1e7 * meters
            0, # alt - Altitude in meters in AMSL altitude(not WGS84 if absolute or relative)
                        # altitude above terrain if GLOBAL_TERRAIN_ALT_INT
            velocity_x, # X velocity in NED frame in m/s
            velocity_y, # Y velocity in NED frame in m/s
            velocity_z, # Z velocity in NED frame in m/s
            0, 0, 0,    # afx, afy, afz acceleration (not supported yet, ignored in GCS_Mavlink)
            0, 0)       # yaw, yaw_rate (not supported yet, ignored in GCS_Mavlink)
        # send command to vehicle
        self.vehicle.send_mavlink(msg)
        self.vehicle.flush()

    def set_yaw(self, heading, relative=False, direction=0):
        """
        Set the bearing `heading` of the vehicle in degrees. This becomes the yaw of the vehicle (the direction in which it is facing). The `heading` is a bearing, meaning that north is zero degrees and increasing counterclockwise.

        This command works in GUIDED mode and only works after a velocity command has been issued.
        If `relative` is false, `heading` is the number of degrees off from northward direction, clockwise.
        If `relative` is true, the `heading` is still given as a bearing, but respective to the vehicle's current yaw.
        The `direction` gives the direction in which we should rotate: 1 is clockwise and -1 is counter. If `direction is 0, then use the direction in which we reach the requested heading the quickest.
        """

        if direction == 0:
            yaw = self.vehicle.attitude.yaw
            if relative:
                new_yaw = yaw + heading * math.pi/180
            else:
                new_yaw = heading * math.pi/180

            # -1 because the yaw is given as a bearing that increases clockwise 
            # while geometry works with angles that increase counterclockwise.
            direction = -1 * self.geometry.get_direction(yaw, new_yaw)

        if self.is_mock:
            heading = heading * math.pi/180
            if relative:
                self.vehicle.set_target_attitude(yaw=self.vehicle.attitude.yaw + heading, yaw_direction=direction)
            else:
                self.vehicle.set_target_attitude(yaw=heading, yaw_direction=direction)

            return

        if relative:
            is_relative = 1 # yaw relative to direction of travel
        else:
            is_relative = 0 # yaw is an absolute angle

        # Create the CONDITION_YAW command using command_long_encode()
        msg = self.vehicle.message_factory.command_long_encode(
            0, 0,    # target system, target component
            mavutil.mavlink.MAV_CMD_CONDITION_YAW, # command
            0, # confirmation
            heading,     # param 1, yaw in degrees
            1,           # param 2, yaw speed deg/s (ignored)
            direction,   # param 3, direction -1 ccw, 1 cw
            is_relative, # param 4, relative offset 1, absolute angle 0
            0, 0, 0      # param 5 ~ 7 not used
        )

        # Send command to vehicle
        self.vehicle.send_mavlink(msg)
        self.vehicle.flush()

    def return_to_launch(self):
        print("Return to launch")
        self.vehicle.mode = VehicleMode("RTL")
        # Flush to ensure changes are sent to autopilot
        self.vehicle.flush()

class Mission_Auto(Mission):
    """
    A mission that uses the AUTO mode to move to fixed locations.
    """

    def setup(self):
        super(Mission_Auto, self).setup()
        self.add_commands(self.environment.get_location())

    def add_commands(self):
        raise NotImplemented("Must be implementen in child class")

    def display(self):
        # Make sure that mission being sent is displayed on console cleanly
        time.sleep(self.settings.get("mission_delay"))
        num_commands = self.vehicle.commands.count
        print("{} commands in the mission!".format(num_commands))

    def start(self):
        # Set mode to AUTO to start mission
        self.vehicle.mode = VehicleMode("AUTO")
        self.vehicle.flush()

    def check_waypoint(self):
        next_waypoint = self.vehicle.commands.next
        distance = self.distance_to_current_waypoint()
        if next_waypoint > 1:
            if distance < self.farness:
                print("Distance to waypoint ({}): {} m".format(next_waypoint, distance))
                if distance < self.closeness:
                    print("Close enough: skip to next waypoint")
                    self.vehicle.commands.next = next_waypoint + 1
                    next_waypoint = next_waypoint + 1

        num_commands = self.vehicle.commands.count
        if next_waypoint >= num_commands:
            print("Exit 'standard' mission when heading for final waypoint ({})".format(num_commands))
            return False

        return True

class Mission_Guided(Mission):
    """
    A mission that uses the GUIDED mode to move on the fly.
    This allows the mission to react to unknown situations determined using sensors.
    """

    def start(self):
        # Set mode to GUIDED. In fact the arming should already have done this, 
        # but it is good to do it here as well.
        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.flush()

# Actual mission implementations

class Mission_Square(Mission_Auto):
    def add_commands(self, start):
        """
        Adds a takeoff command and four waypoint commands to the current mission. 
        The waypoints are positioned to form a square of side length `2*size` around the specified `center` Location.

        The function assumes `vehicle.commands` is the vehicle mission state 
        (you must have called `download_mission` at least once before in the session and after any use of `clear_mission`)
        """
        # Add the commands. The meaning/order of the parameters is documented 
        # in the Command class.
        cmds = self.vehicle.commands
        # Add MAV_CMD_NAV_TAKEOFF command. This is ignored if the vehicle is 
        # already in the air.
        cmds.add(Command(0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 0, self.altitude))

        # Define the four MAV_CMD_NAV_WAYPOINT locations and add the commands
        point1 = self.geometry.get_location_meters(start, self.size, -self.size)
        point2 = self.geometry.get_location_meters(start, self.size, self.size)
        point3 = self.geometry.get_location_meters(start, -self.size, self.size)
        point4 = self.geometry.get_location_meters(start, -self.size, -self.size)
        cmds.add(Command(0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 0, 0, 0, 0, 0, point1.lat, point1.lon, self.altitude))
        cmds.add(Command(0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 0, 0, 0, 0, 0, point2.lat, point2.lon, self.altitude))
        cmds.add(Command(0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 0, 0, 0, 0, 0, point3.lat, point3.lon, self.altitude))
        cmds.add(Command(0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 0, 0, 0, 0, 0, point4.lat, point4.lon, self.altitude))
        cmds.add(Command(0, 0, 0, mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT, mavutil.mavlink.MAV_CMD_NAV_WAYPOINT, 0, 0, 0, 0, 0, 0, point1.lat, point1.lon, self.altitude))

        # Send commands to vehicle.
        self.vehicle.flush()

class Mission_Browse(Mission_Guided):
    """
    Mission that stays at a fixed location and scans its surroundings.
    """

    def setup(self):
        super(Mission_Browse, self).setup()
        self.yaw = 0
        self.yaw_angle_step = 10

    def step(self):
        # We stand still and change the angle to look around.
        self.send_global_velocity(0,0,0)
        self.vehicle.flush()
        self.set_yaw(self.yaw, relative=False, direction=1)
        print("Velocity: {} m/s".format(self.vehicle.velocity))
        print("Altitude: {} m".format(self.vehicle.location.alt))
        print("Yaw: {} Expected: {}".format(self.vehicle.attitude.yaw*180/math.pi, self.yaw))

        # When we're standing still, we rotate the vehicle to measure distances 
        # to objects.
        self.yaw = (self.yaw + self.yaw_angle_step) % 360

class Mission_Search(Mission_Browse):
    def setup(self):
        super(Mission_Search, self).setup()
        self.move_distance = 0
        self.start_location = self.environment.get_location()

        self.dists_size = 360 / self.yaw_angle_step
        self.dists = np.zeros(self.dists_size)
        self.dists_done = np.zeros(self.dists_size, dtype=bool)

        self.padding = 4.0
        self.yaw_margin = 5.0 * math.pi/180

    def step(self):
        if self.move_distance > 0:
            moved = self.environment.get_distance(self.start_location)
            d = self.move_distance - moved
            if d <= 0:
                self.move_distance = 0

        if self.move_distance == 0:
            super(Mission_Search, self).step()
            if all(self.dists_done):
                current_location = self.environment.get_location()

                # Find safest "furthest" location (in one line) and move there
                a = self.yaw
                dist = 0
                i = 0
                d_left = 0
                right = 0
                cycle_safe = 0
                safeness = np.zeros(self.dists_size)
                bounds = np.zeros(self.dists_size)
                for d in self.dists:
                    if d == 0:
                        right = right + 1
                    else:
                        dist = d + self.padding + self.closeness
                        angle = (i + right - 1) * self.yaw_angle_step * math.pi/180
                        loc = self.geometry.get_location_angle(current_location, dist, angle)

                        if i == 0:
                            cycle_safe = right
                        elif i == self.dists_size - 1:
                            break
                        else:
                            safeness[i] = right + d_left

                        if self.memory_map.location_in_bounds(loc):
                            d_left = d/float(self.farness)
                        else:
                            d_left = -right

                        safeness[(i + right - 1) % self.dists_size] = right + d_left

                        i = i + right + 1
                        right = 0

                safeness[i % self.dists_size] = right + cycle_safe + d_left

                a = np.argmax(self.dists + safeness)
                dist = self.dists[a]
                if safeness[(a+1) % self.dists_size] > safeness[(a-1) % self.dists_size]:
                    a = a+2
                else:
                    a = a-2

                angle = a * self.yaw_angle_step * math.pi/180
                self.yaw = self.geometry.angle_to_bearing(angle)

                self.move_distance = dist + self.padding + self.closeness
                self.start_location = current_location

                self.dists = np.zeros(self.dists_size)
                self.dists_done = np.zeros(self.dists_size, dtype=bool)

                self.set_yaw(self.yaw * 180/math.pi, relative=False)
                self.set_speed(self.speed)
                self.vehicle.commands.goto(self.geometry.get_location_angle(current_location, self.move_distance, angle))

    def check_sensor_distance(self, sensor_distance, yaw, pitch):
        close = super(Mission_Search, self).check_sensor_distance(sensor_distance, yaw, pitch)

        angle_deg = yaw * 180/math.pi
        a = int(angle_deg / self.yaw_angle_step)
        self.dists_done[a] = True
        if sensor_distance < self.farness:
            self.dists[a] = sensor_distance

        if sensor_distance < self.padding + self.closeness:
            if self.geometry.check_angle(self.yaw, self.environment.get_yaw(), self.yaw_margin):
                self.move_distance = 0

        return close
