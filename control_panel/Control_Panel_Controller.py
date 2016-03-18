from Control_Panel_View import Control_Panel_View_Name
from Control_Panel_Loading_View import Control_Panel_Loading_View
from Control_Panel_Reconstruction_View import Control_Panel_Reconstruction_View
from Control_Panel_Waypoints_View import Control_Panel_Waypoints_View
from ..core.Thread_Manager import Thread_Manager
from ..core.USB_Manager import USB_Manager
from ..settings import Arguments
from ..zigbee.XBee_Sensor_Physical import XBee_Sensor_Physical

class Control_Panel_Controller(object):
    def __init__(self, central_widget, window):
        """
        Initialize the control panel controller.
        """

        # Set the central widget and window for loading views.
        self.central_widget = central_widget
        self.window = window

        # Create arguments (for obtaining various settings in views)
        # and a USB manager (for checking insertion of XBee devices).
        self.arguments = Arguments("settings.json", [])
        self.thread_manager = Thread_Manager()
        self.usb_manager = USB_Manager()
        self.usb_manager.index()
        self.xbee = XBee_Sensor_Physical(self.arguments, self.thread_manager,
                                         self.usb_manager, self._get_location,
                                         self._receive, self._location_valid)

        self._packet_callbacks = {}

        # Show the loading view (default).
        self.show_view(Control_Panel_View_Name.WAYPOINTS)

    def _get_location(self):
        return (0, 0)

    def _receive(self, packet):
        specification = packet.get("specification")
        if specification in self_packet_callbacks:
            callback = self._packet_callbacks[specification]
            callback()

    def _location_valid(self, other_valid=None):
        return False

    def add_packet_callback(self, specification, callback):
        if not hasattr(callback, "__call__"):
            raise TypeError("The provided callback is not callable.")

        self._packet_callbacks[specification] = callback

    def show_view(self, name):
        """
        Show a new view, identified by `name`, and clear the current view.
        """

        views = {
            Control_Panel_View_Name.LOADING: Control_Panel_Loading_View,
            Control_Panel_View_Name.RECONSTRUCTION: Control_Panel_Reconstruction_View,
            Control_Panel_View_Name.WAYPOINTS: Control_Panel_Waypoints_View
        }

        if name not in views:
            raise ValueError("Unknown view name specified.")

        view = views[name](self)
        view.clear(self.central_widget.layout())
        view.show()
