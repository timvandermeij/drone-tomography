from mock import patch, MagicMock
from ..core.Threadable import Threadable
from ..core.Thread_Manager import Thread_Manager
from ..settings import Arguments
from core_thread_manager import ThreadableTestCase

class TestControlInfraredSensor(ThreadableTestCase):
    def setUp(self):
        super(TestControlInfraredSensor, self).setUp()

        # We need to mock the pylirc module as we do not want to use actual 
        # LIRC communication. We assume the pylirc module works as expected.
        self.pylirc_mock = MagicMock()
        modules = {
            'pylirc': self.pylirc_mock
        }

        self._pylirc_patcher = patch.dict('sys.modules', modules)
        self._pylirc_patcher.start()

        # Skip configuration checks since we emulate the behavior of LIRC. We 
        # test the configuration checks in `test_initialization`. This also
        # requires us to import the module within the tests instead of globally.
        from ..control.Infrared_Sensor import Infrared_Sensor
        self.old_configure = Infrared_Sensor._configure
        Infrared_Sensor._configure = MagicMock()

        self.thread_manager = Thread_Manager()

        self.arguments = Arguments("settings.json", [])
        self.settings = self.arguments.get_settings("infrared_sensor")
        self.infrared_sensor = Infrared_Sensor(self.settings, self.thread_manager)
        self.mock_callback = MagicMock()

    def tearDown(self):
        super(TestControlInfraredSensor, self).tearDown()

        # Reset mock configure method so that we do not lose the original 
        # method during multiple tests.
        from ..control.Infrared_Sensor import Infrared_Sensor
        Infrared_Sensor._configure = self.old_configure

        # Stop the pylirc module patcher
        self._pylirc_patcher.stop()

    def test_initialization(self):
        # Test initialization of infrared sensor with a local import and 
        # a local thread manager rather than the ones already created at setUp.
        from ..control.Infrared_Sensor import Infrared_Sensor
        thread_manager = Thread_Manager()

        # Test whether we can pass Arguments to the infrared sensor.
        with patch.object(Infrared_Sensor, '_configure'):
            infrared_sensor = Infrared_Sensor(self.arguments, thread_manager)
            self.assertEqual(infrared_sensor._settings, self.settings)

        # Test whether other types for arguments and settings are rejected.
        with self.assertRaises(ValueError):
            Infrared_Sensor(None, thread_manager)

    def test_configure(self):
        # Test initialization of infrared sensor with a local import and 
        # a local thread manager rather than the ones already created at setUp.
        from ..control.Infrared_Sensor import Infrared_Sensor
        thread_manager = Thread_Manager()

        Infrared_Sensor._configure = self.old_configure

        # Test whether we check that we have /etc/lirc installed
        methods = {
            'isdir.return_value': False
        }
        with patch('os.path', **methods) as path_mock:
            with self.assertRaisesRegexp(OSError, "not installed"):
                Infrared_Sensor(self.settings, thread_manager)

            path_mock.isdir.assert_called_once_with("/etc/lirc")

        # Test whether we detect when the remote configuration file is already 
        # placed in the /etc/lirc directory.
        methods = {
            'isdir.return_value': True,
            'isfile.return_value': True
        }
        with patch('os.path', **methods) as path_mock:
            Infrared_Sensor(self.settings, thread_manager)
            self.assertEqual(path_mock.isfile.call_count, 1)
            args = path_mock.isfile.call_args[0]
            self.assertEqual(len(args), 1)
            self.assertTrue(args[0].startswith("/etc/lirc/lircd.conf.d/"))

        # Test whether we check that the remote exists
        methods = {
            'isdir.return_value': True,
            'isfile.return_value': False
        }
        with patch('os.path', **methods) as path_mock:
            with self.assertRaisesRegexp(OSError, r".*\.lircd\.conf.* does not exist"):
                Infrared_Sensor(self.settings, thread_manager)

            self.assertEqual(path_mock.isfile.call_count, 2)
            args = path_mock.isfile.call_args[0]
            self.assertEqual(len(args), 1)
            self.assertRegexpMatches(args[0], r"/remotes/.*\.lircd\.conf$")

        # Test whether we check that the configuration file exists
        methods = {
            'isdir.return_value': True,
            'isfile.side_effect': lambda f: "/remotes/" in f and f.endswith(".lircd.conf")
        }
        with patch('os.path', **methods) as path_mock:
            with self.assertRaisesRegexp(OSError, r".*\.lircrc.* does not exist"):
                Infrared_Sensor(self.settings, thread_manager)

            self.assertEqual(path_mock.isfile.call_count, 3)
            args = path_mock.isfile.call_args[0]
            self.assertRegexpMatches(args[0], r"/remotes/.*\.lircrc$")

    def test_configure_copy(self):
        # Test initialization of infrared sensor with a local import and 
        # a local thread manager rather than the ones already created at setUp.
        from ..control.Infrared_Sensor import Infrared_Sensor
        thread_manager = Thread_Manager()

        Infrared_Sensor._configure = self.old_configure

        # Test whether the remote file is copied to the LIRC root.
        methods = {
            'isdir.return_value': True,
            'isfile.side_effect': lambda f: "/remotes/" in f
        }
        with patch('os.path', **methods):
            with patch('shutil.copyfile') as copy_mock:
                Infrared_Sensor(self.settings, thread_manager)
                self.assertEqual(copy_mock.call_count, 1)
                args = copy_mock.call_args[0]
                self.assertRegexpMatches(args[0], r"/remotes/.*\.lircd\.conf$")
                self.assertTrue(args[1].startswith("/etc/lirc/lircd.conf.d"))

            with patch('shutil.copyfile', side_effect=IOError):
                with self.assertRaisesRegexp(OSError, "not writable"):
                    Infrared_Sensor(self.settings, thread_manager)

    def test_register(self):
        # We must have an existing button.
        with self.assertRaises(KeyError):
            self.infrared_sensor.register("!nonexistent malformed button!", self.mock_callback)

        # We must have a (normal) callback.
        with self.assertRaises(ValueError):
            self.infrared_sensor.register("start", None)

        # We must have callable functions for all given callbacks.
        with self.assertRaises(ValueError):
            self.infrared_sensor.register("stop", self.mock_callback, "not a function")

    def test_callbacks(self):
        # Test normal event callback.
        self.infrared_sensor.register("start", self.mock_callback)

        self.infrared_sensor._handle_lirc_code(None)
        self.assertFalse(self.mock_callback.called)
        self.infrared_sensor._handle_lirc_code(['start'])
        self.assertEqual(self.mock_callback.call_count, 1)

        # Test additional release callback.
        self.mock_callback.reset_mock()
        mock_callback = MagicMock()
        mock_release_callback = MagicMock()

        self.infrared_sensor.register("stop", mock_callback, mock_release_callback)

        self.infrared_sensor._handle_lirc_code(None)
        self.assertFalse(mock_callback.called)
        self.assertFalse(mock_release_callback.called)

        self.infrared_sensor._handle_lirc_code(['stop'])
        self.assertEqual(mock_callback.call_count, 1)
        self.assertFalse(mock_release_callback.called)

        self.infrared_sensor._handle_lirc_code(None)
        self.infrared_sensor._handle_lirc_code(None)
        self.assertEqual(mock_callback.call_count, 1)
        self.assertEqual(mock_release_callback.call_count, 1)
        # Start button was not pressed.
        self.assertFalse(self.mock_callback.called)

    @patch('thread.start_new_thread')
    def test_activate(self, thread_mock):
        self.infrared_sensor.activate()
        self.assertEqual(self.pylirc_mock.init.call_count, 1)
        args = self.pylirc_mock.init.call_args[0]
        self.assertRegexpMatches(args[1], r"/remotes/.*\.lircrc")
        thread_mock.assert_called_once_with(self.infrared_sensor._loop, ())
        self.assertTrue(self.infrared_sensor._active)

    @patch.object(Threadable, 'interrupt')
    def test_loop(self, interrupt_mock):
        self.infrared_sensor._active = True
        with patch.object(self.infrared_sensor, '_handle_lirc_code') as handle_mock:
            with patch('time.sleep', side_effect=ValueError) as sleep_mock:
                self.infrared_sensor._loop()
                self.assertEqual(sleep_mock.call_count, 1)

            handle_mock.assert_called_once_with(self.pylirc_mock.nextcode.return_value)
            interrupt_mock.assert_called_once_with()

    def test_deactivate(self):
        self.infrared_sensor._active = True
        self.infrared_sensor.deactivate()
        self.assertFalse(self.infrared_sensor._active)
        self.pylirc_mock.exit.assert_called_once_with()
