import itertools
from collections import deque
from mock import patch
from dronekit import LocationLocal
from ..mission.Mission_Fan import Mission_Fan
from ..vehicle.Mock_Vehicle import Mock_Vehicle
from ..vehicle.Robot_Vehicle import Robot_Vehicle, Robot_State
from environment import EnvironmentTestCase

class TestMissionFan(EnvironmentTestCase):
    def setUp(self):
        self.register_arguments([
            "--vehicle-class", "Robot_Vehicle_Arduino",
            "--geometry-class", "Geometry", "--space-size", "4",
            "--number-of-sensors", "2", "--closeness", "0",
            "--rf-sensor-synchronization"
        ], use_infrared_sensor=False)

        super(TestMissionFan, self).setUp()

        self.maxDiff = None

        self.vehicle = self.environment.get_vehicle()

        settings = self.arguments.get_settings("mission")
        self.mission = Mission_Fan(self.environment, settings)
        self.rf_sensor = self.environment.get_rf_sensor()
        # Determine the rounds of the first vehicle, as well as the rounds in 
        # which it waits for the other vehicle. The final point of a round is 
        # added via the wait commands.
        self.wait_commands = 9
        rounds = [
            [(1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (3, 3), (2, 3), (1, 3)],
            [(0, 3)] * (self.wait_commands + 1),
            [(0, 2), (0, 1), (0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (3, 2)],
            [(3, 3)] * (self.wait_commands + 1),
            [(2, 3), (1, 3), (0, 3), (0, 2), (0, 1), (0, 0), (1, 0), (2, 0)],
            [(3, 0)] * (self.wait_commands + 1),
            [(3, 1), (3, 2), (3, 3), (2, 3), (1, 3), (0, 3), (0, 2), (0, 1)],
            [(0, 0)] * (self.wait_commands + 1)
        ]
        self.first_waypoints = list(itertools.chain(*rounds))

    def test_setup_robot_vehicle(self):
        # Check that the mission can only be run using a robot vehicle.
        with self.assertRaises(ValueError):
            vehicle = Mock_Vehicle(self.arguments, self.environment.geometry,
                                   self.environment.import_manager,
                                   self.environment.thread_manager,
                                   self.environment.usb_manager)
            self.mission.vehicle = vehicle
            with patch('sys.stdout'):
                self.mission.setup()

    def test_setup_location(self):
        # Check that the mission requires a valid starting location.
        with self.assertRaises(ValueError):
            self.vehicle._location = (4, 2)
            with patch('sys.stdout'):
                self.mission.setup()

    def test_setup_init(self):
        with patch('sys.stdout'):
            self.mission.setup()

        # Check first vehicle's state.
        self.assertEqual(self.vehicle.location, LocationLocal(0, 0, 0))
        self.assertEqual(self.mission.id, 0)
        self.assertEqual(self.mission.size, 4)
        self.assertIsInstance(self.mission.chain, deque)
        # 4 sides, 2 rounds per side
        self.assertEqual(self.mission.round_number, 8)
        self.assertIsInstance(self.mission.waypoints, list)
        waypoints = list(self.mission.waypoints)
        self.assertEqual(waypoints, self.first_waypoints)

        # Check second vehicle's state.
        self.vehicle._location = (0, 1)
        with patch('sys.stdout'):
            self.mission.setup()

        waypoints = list(self.mission.waypoints)

        rounds = [
            [(0, 1)] * self.wait_commands,
            [(0, 0), (1, 0), (2, 0), (3, 0), (3, 1), (3, 2), (3, 3), (2, 3)],
            [(1, 3)] * (self.wait_commands + 1),
            [(0, 3), (0, 2), (0, 1), (0, 0), (1, 0), (2, 0), (3, 0), (3, 1)],
            [(3, 2)] * (self.wait_commands + 1),
            [(3, 3), (2, 3), (1, 3), (0, 3), (0, 2), (0, 1), (0, 0), (1, 0)],
            [(2, 0)] * (self.wait_commands + 1),
            [(3, 0), (3, 1), (3, 2), (3, 3), (2, 3), (1, 3), (0, 3), (0, 2)],
            [(0, 1)]
        ]
        second_waypoints = list(itertools.chain(*rounds))

        self.assertEqual(waypoints, second_waypoints)

    def test_get_points(self):
        with patch('sys.stdout'):
            self.mission.setup()

        points = self.mission.get_points()
        self.assertEqual(len(points), len(self.first_waypoints))
        for point, waypoint in zip(points, self.first_waypoints):
            self.assertEqual(point, LocationLocal(waypoint[0], waypoint[1], 0.0))

    @patch.object(Robot_Vehicle, "_state_loop")
    def test_check_waypoint(self, state_loop_mock):
        with patch('sys.stdout'):
            self.mission.setup()
            self.mission.arm_and_takeoff()
            self.mission.start()

        self.assertEqual(self.vehicle.mode.name, "AUTO")
        self.assertTrue(self.vehicle.armed)
        state_loop_mock.assert_called_once_with()
        self.assertEqual(self.vehicle._waypoints,
                         list(itertools.chain(*[[waypoint, None] for waypoint in self.first_waypoints])))
        self.assertEqual(self.vehicle.get_waypoint(), None)

        with patch('sys.stdout'):
            self.mission.check_waypoint()

        self.vehicle._check_state()
        self.assertEqual(self.vehicle._state.name, "move")
        self.assertEqual(self.vehicle._current_waypoint, 0)
        self.assertEqual(self.vehicle.get_waypoint(), LocationLocal(1, 0, 0))
        self.assertNotEqual(self._ttl_device.readline(), "")

        self.vehicle._location = (1, 0)
        self.vehicle._state = Robot_State("intersection")
        with patch('sys.stdout'):
            self.mission.check_waypoint()

        # The mission waits for the other RF sensor to send a valid location packet.
        self.vehicle._check_state()
        self.assertEqual(self.vehicle._current_waypoint, 1)
        self.assertEqual(self.vehicle.get_waypoint(), None)

        other_id = self.rf_sensor.id + 1
        self.environment.set_waypoint_valid()
        self.assertTrue(self.location_valid(True, other_id=other_id))
        self.assertTrue(self.location_valid(False, other_id=other_id,
                                            other_index=1, other_valid=True,
                                            other_valid_pair=True))
        self.assertTrue(self.location_valid(True, other_id=other_id))

        with patch('sys.stdout'):
            self.mission.check_waypoint()

        self.vehicle._check_state()
        self.assertEqual(self.vehicle._current_waypoint, 2)
        self.assertEqual(self.vehicle.get_waypoint(), LocationLocal(2, 0, 0))
