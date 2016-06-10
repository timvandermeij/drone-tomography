import time

class Monitor(object):
    """
    Mission monitor class.

    Tracks sensors and mission actions in a stepwise fashion.
    """

    def __init__(self, mission, environment):
        self.mission = mission

        self.environment = environment
        arguments = self.environment.get_arguments()
        self.settings = arguments.get_settings("mission_monitor")

        # Seconds to wait before monitoring again
        self.step_delay = self.settings.get("step_delay")

        self.sensors = self.environment.get_distance_sensors()
        self.rf_sensor = self.environment.get_rf_sensor()

        self.colors = ["red", "purple", "black"]

        self.memory_map = None
        self.plot = None

    def get_delay(self):
        return self.step_delay

    def use_viewer(self):
        return self.settings.get("viewer")

    def setup(self):
        self.memory_map = self.mission.get_memory_map()

        if self.settings.get("plot"):
            # Setup memory map plot
            from Plot import Plot
            self.plot = Plot(self.environment, self.memory_map)

        if self.rf_sensor is not None:
            self.rf_sensor.activate()

    def step(self, add_point=None):
        """
        Perform one step of a monitoring loop.

        `add_point` can be a callback function that accepts a Location object
        for a detected point from the distance sensors.

        Returns `Fase` if the loop should be halted.
        """

        # Put our current location on the map for visualization. Of course, 
        # this location is also "safe" since we are flying there.
        vehicle_idx = self.memory_map.get_index(self.environment.get_location())
        try:
            self.memory_map.set(vehicle_idx, -1)
        except KeyError:
            print('Warning: Outside of memory map')

        self.mission.step()

        i = 0
        for sensor in self.sensors:
            yaw = sensor.get_angle()
            pitch = sensor.get_pitch()
            sensor_distance = sensor.get_distance()

            if self.mission.check_sensor_distance(sensor_distance, yaw, pitch):
                location = self.memory_map.handle_sensor(sensor_distance, yaw)
                if add_point is not None:
                    add_point(location)
                if self.plot:
                    # Display the edge of the simulated object that is 
                    # responsible for the measured distance, and consequently 
                    # the point itself. This should be the closest "wall" in 
                    # the angle's direction. This is again a "cheat" for 
                    # checking if walls get visualized correctly.
                    sensor.draw_current_edge(self.plot.get_plot(), self.memory_map, self.colors[i % len(self.colors)])

                print("=== [!] Distance to object: {} m (yaw {}, pitch {}) ===".format(sensor_distance, yaw, pitch))

            i = i + 1

        # Display the current memory map interactively.
        if self.plot:
            self.plot.plot_lines(self.mission.get_waypoints())
            self.plot.display()

        if not self.mission.check_waypoint():
            return False

        # Remove the vehicle from the current location. We set it to "safe" 
        # since there is no object here.
        try:
            self.memory_map.set(vehicle_idx, 0)
        except KeyError:
            pass

        return True

    def sleep(self):
        time.sleep(self.step_delay)

    def start(self):
        self.mission.start()

        if self.rf_sensor is not None:
            self.rf_sensor.start()

    def stop(self):
        self.mission.stop()

        if self.rf_sensor is not None:
            self.rf_sensor.stop()

        if self.plot:
            self.plot.close()
