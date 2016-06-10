from mock import patch, MagicMock
from ..core.Import_Manager import Import_Manager
from ..core.Thread_Manager import Thread_Manager
from ..distance.Distance_Sensor_Simulator import Distance_Sensor_Simulator
from ..environment.Environment import Environment
from ..geometry.Geometry_Spherical import Geometry_Spherical
from ..settings import Arguments
from ..trajectory.Servo import Servo
from ..vehicle.Mock_Vehicle import Mock_Vehicle
from ..zigbee.Packet import Packet
from ..zigbee.XBee_Sensor_Simulator import XBee_Sensor_Simulator
from geometry import LocationTestCase
from settings import SettingsTestCase
from core_thread_manager import ThreadableTestCase
from core_usb_manager import USBManagerTestCase
from core_wiringpi import WiringPiTestCase

class EnvironmentTestCase(LocationTestCase, SettingsTestCase,
                          ThreadableTestCase, USBManagerTestCase,
                          WiringPiTestCase):
    """
    Test case class for tests that make use of the `Environment` class,
    including mission and distance sensor tests.

    This class handles initializing the settings in a generic manner and
    providing various means of simulating sensors and other modules.
    """

    def __init__(self, *a, **kw):
        super(EnvironmentTestCase, self).__init__(*a, **kw)

        self._argv = []
        self._modules = {}
        self._simulated = True

    def register_arguments(self, argv, simulated=True, distance_sensors=None,
                           use_infrared_sensor=True):
        self._argv = argv
        self._argv.extend(["--rf-sensor-class", "XBee_Sensor_Simulator", "--rf-sensor-id", "1"])

        self._simulated = simulated
        # WiringPiTestCase provides a patcher for RPi.GPIO, which is necessary 
        # when not in simulation mode to be able to run those tests on PC. 
        # Additionally, it always handles the WiringPi setup singleton.
        self.set_rpi_patch(rpi_patch=not simulated)

        self._modules = {}

        if use_infrared_sensor:
            # We need to mock the Infrared_Sensor module as it is only 
            # available when LIRC is installed which is not a requirement for 
            # running tests.
            package = __package__.split('.')[0]
            self._modules[package + '.control.Infrared_Sensor'] = MagicMock()

            self._argv.append("--infrared-sensor")
        else:
            self._argv.append("--no-infrared-sensor")

        if distance_sensors is not None:
            self._argv.append("--distance-sensors")
            self._argv.extend([str(sensor) for sensor in distance_sensors])

    def setUp(self):
        super(EnvironmentTestCase, self).setUp()

        self.arguments = Arguments("settings.json", self._argv)

        if self._modules:
            self._module_patcher = patch.dict('sys.modules', self._modules)
            self._module_patcher.start()

        self.environment = Environment.setup(self.arguments,
                                             usb_manager=self.usb_manager,
                                             simulated=self._simulated)

        # Make the environment thread manager available to the tearDown method 
        # of the ThreadableTestCase.
        self.thread_manager = self.environment.thread_manager

    def tearDown(self):
        super(EnvironmentTestCase, self).tearDown()
        if self._modules:
            self._module_patcher.stop()

class TestEnvironment(EnvironmentTestCase):
    def setUp(self):
        self.register_arguments([
            "--geometry-class", "Geometry_Spherical",
            "--vehicle-class", "Mock_Vehicle", "--number-of-sensors", "3"
        ], distance_sensors=[0, 90], use_infrared_sensor=True)

        super(TestEnvironment, self).setUp()

    def test_setup(self):
        self.assertIsInstance(self.environment, Environment)
        self.assertIsInstance(self.environment.vehicle, Mock_Vehicle)
        self.assertIsInstance(self.environment.geometry, Geometry_Spherical)
        self.assertIsInstance(self.environment.import_manager, Import_Manager)
        self.assertIsInstance(self.environment.thread_manager, Thread_Manager)
        self.assertEqual(self.environment.usb_manager, self.usb_manager)
        self.assertEqual(self.environment.arguments, self.arguments)
        self.assertTrue(self.environment.settings.get("infrared_sensor"))

        self.assertEqual(self.environment.get_vehicle(), self.environment.vehicle)
        self.assertEqual(self.environment.get_geometry(), self.environment.geometry)
        self.assertEqual(self.environment.get_arguments(), self.environment.arguments)

        self.assertEqual(self.environment.get_import_manager(), self.environment.import_manager)
        self.assertEqual(self.environment.get_thread_manager(), self.environment.thread_manager)
        self.assertEqual(self.environment.get_usb_manager(), self.environment.usb_manager)

        distance_sensors = self.environment.get_distance_sensors()
        expected_angles = [0, 90]
        self.assertEqual(len(distance_sensors), len(expected_angles))
        for i, expected_angle in enumerate(expected_angles):
            self.assertIsInstance(distance_sensors[i], Distance_Sensor_Simulator)
            self.assertEqual(distance_sensors[i].id, i)
            self.assertEqual(distance_sensors[i].angle, expected_angle)

        for servo in self.environment.get_servos():
            self.assertIsInstance(servo, Servo)

        self.assertIsInstance(self.environment.get_rf_sensor(), XBee_Sensor_Simulator)
        self.assertIsNotNone(self.environment.get_infrared_sensor())

    def test_packet_action(self):
        # Callback must be callable
        with self.assertRaises(TypeError):
            self.environment.add_packet_action("waypoint_add", "no_function")

        mock_callback = MagicMock()
        self.environment.add_packet_action("waypoint_add", mock_callback)
        # Not allowed to add more than one callback for a packet specification.
        with self.assertRaises(KeyError):
            self.environment.add_packet_action("waypoint_add", MagicMock())

        # Callback is called for correct specification.
        packet = Packet()
        packet.set("specification", "waypoint_add")
        packet.set("latitude", 12.345)
        packet.set("longitude", 32.109)
        packet.set("to_id", 1)

        self.environment.receive_packet(packet)
        mock_callback.assert_called_once_with(packet)

        # Callback is not called for another specification.
        mock_callback.reset_mock()
        packet = Packet()
        packet.set("specification", "waypoint_clear")
        packet.set("to_id", 1)

        self.environment.receive_packet(packet)
        mock_callback.assert_not_called()

    def test_location(self):
        location = self.environment.vehicle.location.global_relative_frame
        self.assertEqual(location, self.environment.get_location())
        raw_location, waypoint_index = self.environment.get_raw_location()
        self.assertEqual((location.lat, location.lon), raw_location)
        self.assertEqual(0, waypoint_index)

    def test_location_valid(self):
        rf_sensor = self.environment.get_rf_sensor()

        self.assertEqual(self.environment._valid_measurements, {})
        self.assertEqual(self.environment._required_sensors, set(range(1, rf_sensor.number_of_sensors + 1)))

        self.assertTrue(self.environment.location_valid())
        self.assertFalse(self.environment.is_measurement_valid())
        self.assertEqual(self.environment._valid_measurements, {rf_sensor.id: 0})

        self.assertTrue(self.environment.location_valid(other_valid=True, other_id=rf_sensor.id + 1, other_index=0))
        self.assertFalse(self.environment.is_measurement_valid())
        self.assertEqual(self.environment._valid_measurements, {rf_sensor.id: 0, rf_sensor.id + 1: 0})

        self.assertTrue(self.environment.location_valid(other_valid=True, other_id=rf_sensor.id + 2, other_index=0))
        self.assertTrue(self.environment.is_measurement_valid())

        # Requiring a specific set of sensors
        self.environment.invalidate_measurement(required_sensors=[rf_sensor.id + 1])
        self.assertFalse(self.environment.is_measurement_valid())

        self.assertTrue(self.environment.location_valid(other_valid=True, other_id=rf_sensor.id + 1, other_index=0))
        self.assertTrue(self.environment.is_measurement_valid())
