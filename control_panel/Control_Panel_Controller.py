# Core imports
import re
import sys
import traceback
from collections import OrderedDict
from functools import partial
from PyQt4 import QtCore, QtGui

# Markdown imports
import markdown
from mdx_partial_gfm import PartialGithubFlavoredMarkdownExtension

# Package imports
from Control_Panel_View import Control_Panel_View_Name
from Control_Panel_Devices_View import Control_Panel_Devices_View
from Control_Panel_Loading_View import Control_Panel_Loading_View
from Control_Panel_Planning_View import Control_Panel_Planning_View
from Control_Panel_Reconstruction_View import Control_Panel_Reconstruction_View
from Control_Panel_Settings_View import Control_Panel_Settings_View
from Control_Panel_Waypoints_View import Control_Panel_Waypoints_View
from ..core.Import_Manager import Import_Manager
from ..core.Thread_Manager import Thread_Manager
from ..core.USB_Manager import USB_Manager
from ..settings import Arguments

class Control_Panel_Controller(object):
    def __init__(self, app, central_widget, window):
        """
        Initialize the control panel controller.
        """

        self.app = app
        self.central_widget = central_widget
        self.window = window
        self._current_view = None
        self._current_view_name = None
        self._view_actions = {}

        # Create arguments (for obtaining various settings in views)
        # and a USB manager (for checking insertion of RF sensors).
        self.arguments = Arguments("settings.json", self._get_arguments())
        self.import_manager = Import_Manager()
        self.thread_manager = Thread_Manager()
        self.usb_manager = USB_Manager()
        self.usb_manager.index()

        # Initialize the RF sensor for use by specific views.
        self.setup_rf_sensor()

        # Initialize settings components, in-process shared data and Settings 
        # objects for the specific views.
        self._view_components = {
            Control_Panel_View_Name.LOADING: "control_panel_loading",
            Control_Panel_View_Name.DEVICES: "control_panel_devices",
            Control_Panel_View_Name.PLANNING: "control_panel_planning",
            Control_Panel_View_Name.RECONSTRUCTION: "control_panel_reconstruction",
            Control_Panel_View_Name.WAYPOINTS: "control_panel_waypoints",
            Control_Panel_View_Name.SETTINGS: "control_panel_settings"
        }
        self._view_data = dict([(name, {}) for name in self._view_components.iterkeys()])
        self.load_settings()

        # After loading the settings, check if any unknown arguments have been 
        # provided and show help in that case.
        self.arguments.check_help()

        self._help_file = "README.md"

    def _get_arguments(self):
        """
        Retrieve arguments that are related to our settings, not any Qt-specific
        command line arguments (if supported).
        """

        argv = []
        for i, arg in enumerate(self.app.arguments()):
            arg = str(arg)
            if arg.startswith('--') or arg == '-h':
                argv.append(arg)
            elif i == 0 and not arg.startswith('-'):
                argv.append(arg)

        return argv

    def setup_rf_sensor(self):
        """
        Initialize the RF sensor for specific views.
        """

        settings = self.arguments.get_settings("control_panel")
        rf_sensor_class = settings.get("core_rf_sensor_class")
        rf_sensor_type = self.import_manager.load_class(rf_sensor_class,
                                                        relative_module="zigbee")
        self.rf_sensor = rf_sensor_type(self.arguments, self.thread_manager,
                                        self.usb_manager, self._get_location,
                                        self._receive, self._location_valid)

        self._packet_callbacks = {}

    def load_settings(self):
        """
        Initialize `Settings` objects for specific views.
        """

        self._view_settings = {}
        for view, component in self._view_components.iteritems():
            self._view_settings[view] = self.arguments.get_settings(component)

    def _get_location(self):
        return (0, 0)

    def _receive(self, packet):
        """
        Handle a received custom `Packet` object `packet`.
        """

        specification = packet.get("specification")
        if specification in self._packet_callbacks:
            callback = self._packet_callbacks[specification]
            callback(packet)

    def _location_valid(self, other_valid=None, other_id=None, other_index=None):
        return False

    def add_packet_callback(self, specification, callback):
        """
        Register a function `callback` to be called when a packet with
        the given `specification` is received.
        """

        if not hasattr(callback, "__call__"):
            raise TypeError("The provided callback is not callable.")

        self._packet_callbacks[specification] = callback

    def remove_packet_callback(self, specification):
        """
        Unregister the callback for a given packet `specification`.

        If no such callback is registered for that specification, this method
        does nothing.
        """

        if specification in self._packet_callbacks:
            del self._packet_callbacks[specification]

    def get_view_data(self, view, key):
        """
        Retrieve stored data for the given view name `view` in the stored
        variable `key`.
        """

        if view not in self._view_data:
            raise KeyError("Unknown view '{}'".format(view))

        if key not in self._view_data[view]:
            raise KeyError("View '{}' has no stored variable '{}'".format(view, key))

        return self._view_data[view][key]

    def set_view_data(self, view, key, value):
        """
        Alter stored data for the given view name `view` in the stored
        variable `key` to contain the given `value`.
        """

        if view not in self._view_data:
            raise KeyError("Unknown view '{}'".format(view))

        self._view_data[view][key] = value

    def show_view(self, name):
        """
        Show a new view, identified by `name`, and clear the current view.
        """

        # If we select the current view, then we do not need to change views.
        if self._current_view_name == name:
            self._view_actions[name].setChecked(True)
            return

        if self._current_view is not None:
            self._view_data[self._current_view_name] = self._current_view.save()
            self._current_view.clear(self.central_widget.layout())

        if self._current_view_name in self._view_actions:
            self._view_actions[self._current_view_name].setChecked(False)
        if name in self._view_actions:
            self._view_actions[name].setChecked(True)

        views = {
            Control_Panel_View_Name.LOADING: Control_Panel_Loading_View,
            Control_Panel_View_Name.DEVICES: Control_Panel_Devices_View,
            Control_Panel_View_Name.PLANNING: Control_Panel_Planning_View,
            Control_Panel_View_Name.RECONSTRUCTION: Control_Panel_Reconstruction_View,
            Control_Panel_View_Name.WAYPOINTS: Control_Panel_Waypoints_View,
            Control_Panel_View_Name.SETTINGS: Control_Panel_Settings_View
        }

        try:
            if name not in views:
                raise ValueError("Unknown view name specified.")

            view = views[name](self, self._view_settings[name])
            self._current_view = view
            self._current_view_name = name
            view.load(self._view_data[name])
            view.show()
        except:
            self.thread_manager.destroy()
            self.usb_manager.clear()

            QtGui.QMessageBox.critical(self.central_widget, "Internal error",
                                       traceback.format_exc() + "\nThe application will now exit.")
            self.window.close()
            sys.exit(1)

    def add_menu_bar(self):
        """
        Create a menu bar for the window.
        """

        if self.window._menu_bar is not None:
            self.window._menu_bar.show()
            return

        self.window._menu_bar = self.window.menuBar()

        # Views that are visible in the menu and their action labels.
        view_names = OrderedDict([
            (Control_Panel_View_Name.DEVICES, "Devices"),
            (Control_Panel_View_Name.PLANNING, "Planning"),
            (Control_Panel_View_Name.RECONSTRUCTION, "Reconstruction"),
            (Control_Panel_View_Name.WAYPOINTS, "Waypoints"),
            (Control_Panel_View_Name.SETTINGS, "Settings")
        ])

        view_menu = self.window._menu_bar.addMenu("View")
        self._view_actions = {}
        for view_name, view_label in view_names.iteritems():
            action = QtGui.QAction(view_label, self.window)
            action.triggered.connect(partial(self.show_view, view_name))
            action.setCheckable(True)
            if view_name == self._current_view_name:
                action.setChecked(True)

            view_menu.addAction(action)
            self._view_actions[view_name] = action

        # Add a help menu
        help_menu = self.window._menu_bar.addMenu("Help")

        help_action = QtGui.QAction("Contents", self.window)
        help_action.setShortcut(QtCore.Qt.Key_F1)
        help_action.triggered.connect(self._show_help)

        help_menu.addAction(help_action)

    def _show_help(self):
        dialog = QtGui.QDialog(self.central_widget)
        dialog.setWindowTitle("Help")

        with open(self._help_file, "r") as readme_file:
            readme_text = readme_file.read()

        md = markdown.Markdown(extensions=[
            PartialGithubFlavoredMarkdownExtension(), "markdown.extensions.toc"
        ])
        readme_text = re.sub(r'(\[!.*)', '[TOC]', readme_text)
        html = md.convert(readme_text)

        textBrowser = QtGui.QTextBrowser()
        textBrowser.setSource(QtCore.QUrl(self._help_file))
        textBrowser.setHtml(html)
        textBrowser.setOpenLinks(False)
        textBrowser.anchorClicked.connect(partial(self._click_help, textBrowser))

        dialogButtons = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok)
        dialogButtons.accepted.connect(dialog.accept)

        dialogLayout = QtGui.QVBoxLayout()
        dialogLayout.addWidget(textBrowser)
        dialogLayout.addWidget(dialogButtons)

        dialog.setLayout(dialogLayout)
        windowSize = self.central_widget.size()
        dialog.setMinimumHeight(windowSize.height() / 2)
        dialog.setMinimumWidth(windowSize.width() / 2)

        dialog.exec_()

    def _click_help(self, textBrowser, link):
        linkWithoutFragment = textBrowser.source().resolved(link)
        linkWithoutFragment.setFragment(QtCore.QString())

        if textBrowser.source() == linkWithoutFragment:
            if link.hasFragment():
                textBrowser.scrollToAnchor(link.fragment())
        else:
            QtGui.QDesktopServices.openUrl(link)
