from collections import deque
from mock import patch
from dronekit import LocationLocal
from ..mission.Mission_Calibrate import Mission_Calibrate
from ..vehicle.Mock_Vehicle import Mock_Vehicle
from environment import EnvironmentTestCase

class TestMissionCalibrate(EnvironmentTestCase):
    def setUp(self):
        self.register_arguments([
            "--vehicle-class", "Robot_Vehicle_Arduino",
            "--geometry-class", "Geometry", "--space-size", "5",
            "--number-of-sensors", "2", "--closeness", "0",
            "--rf-sensor-synchronization"
        ], use_infrared_sensor=False)

        super(TestMissionCalibrate, self).setUp()

        self.vehicle = self.environment.get_vehicle()

        settings = self.arguments.get_settings("mission")
        self.mission = Mission_Calibrate(self.environment, settings)
        self.first_waypoints = [
            (1, 0), (2, 0), (3, 0), (4, 0),
            (4, 1), (4, 2), (4, 3), (4, 4),
            (3, 4), (2, 4), (1, 4), (0, 4),
            (0, 3), (0, 2)
        ]

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

    def test_setup(self):
        with patch('sys.stdout'):
            self.mission.setup()

        # Check first vehicle's state.
        self.assertEqual(self.vehicle.location, LocationLocal(0, 0, 0))
        self.assertEqual(self.mission.id, 0)
        self.assertEqual(self.mission.size, 5)
        self.assertIsInstance(self.mission.chain, deque)
        self.assertEqual(self.mission.round_number, 16) # 4 ** 2
        self.assertEqual(self.mission.chain, deque(
            [(0, 0)] + self.first_waypoints + [(0, 1)]
        ))
        self.assertIsInstance(self.mission.waypoints, list)
        self.assertEqual(len(self.mission.waypoints), 16 * 14) # (4**2)*(4*4-2)

        wplen = len(self.first_waypoints)
        self.assertEqual(self.mission.waypoints[0:wplen], self.first_waypoints)
        self.assertEqual(self.mission.waypoints[wplen:wplen*2], [(0, 2)]*wplen)
        self.assertEqual(self.mission.waypoints[wplen*2:wplen*3],
                         [(0, 1), (0, 0)] + self.first_waypoints[:-2])

        # Check second vehicle's state.
        self.vehicle._location = (0, 1)
        with patch('sys.stdout'):
            self.mission.setup()

        self.assertEqual(self.mission.id, 1)
        self.assertEqual(self.mission.round_number, 16)

        self.assertEqual(len(self.mission.waypoints), 16 * 14) # (4**2)*(4*4-2)
        self.assertEqual(len(self.mission.get_points()), 16 * 14)

        self.assertEqual(self.mission.waypoints[0:wplen], [(0, 1)]*wplen)
        self.assertEqual(self.mission.waypoints[wplen:wplen*2],
                         [(0, 0)] + self.first_waypoints[:-1])
        self.assertEqual(self.mission.waypoints[wplen*2:wplen*3], [(0, 3)]*wplen)
