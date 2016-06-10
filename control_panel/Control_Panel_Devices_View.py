from PyQt4 import QtCore, QtGui
from Control_Panel_View import Control_Panel_View

class Device_Category(object):
    COORDINATOR = 0
    END_DEVICE = 2

class Device(object):
    def __init__(self, name, id, category):
        self.name = name
        self.id = id
        self.category = category
        self.address = "-"
        self.joined = False

class Control_Panel_Devices_View(Control_Panel_View):
    def __init__(self, controller, settings):
        super(Control_Panel_Devices_View, self).__init__(controller, settings)

        self._updated = False
        self._timer = None
        self._discover_interval = self._settings.get("devices_discover_delay")
        self._tree_view = None
        self._devices = []

    def load(self, data):
        if "devices" in data:
            self._devices = data["devices"]
            return

        self._devices = [
            Device("Ground station", 0, Device_Category.COORDINATOR)
        ]

        for index in xrange(1, self._controller.rf_sensor.number_of_sensors + 1):
            self._devices.append(Device("Vehicle {}".format(index), index,
                                        Device_Category.END_DEVICE))

    def save(self):
        return {
            "devices": self._devices
        }

    def show(self):
        """
        Show the devices view.
        """

        self._add_menu_bar()

        # Create the tree view.
        self._tree_view = QtGui.QTreeWidget()

        # Create the header for the tree view.
        header = QtGui.QTreeWidgetItem(["Device", "Property value"])
        self._tree_view.setHeaderItem(header)
        self._tree_view.header().setResizeMode(0, QtGui.QHeaderView.Stretch)

        # Refresh immediately to fill the tree view with the devices and to 
        # discover any vehicles that are already connected.
        self._refresh()

        # Create the refresh button.
        refresh_button = QtGui.QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh)

        # Create the layout and add the widgets.
        hbox = QtGui.QHBoxLayout()
        hbox.addWidget(refresh_button)
        hbox.addStretch(1)

        vbox = QtGui.QVBoxLayout(self._controller.central_widget)
        vbox.addLayout(hbox)
        vbox.addWidget(self._tree_view)

    def clear(self, layout=None):
        super(Control_Panel_Devices_View, self).clear(layout)
        if self._timer is not None:
            self._timer.stop()

    def _fill(self):
        """
        Fill the tree view with the device information.
        """

        categories = {
            Device_Category.COORDINATOR: "Coordinator",
            Device_Category.END_DEVICE: "End device"
        }

        # Add an entry in the tree view for each device.
        for device in self._devices:
            item = QtGui.QTreeWidgetItem(self._tree_view, [device.name])
            item.addChild(QtGui.QTreeWidgetItem(["ID", str(device.id)]))
            item.addChild(QtGui.QTreeWidgetItem(["Category", categories[device.category]]))
            item.addChild(QtGui.QTreeWidgetItem(["Address", device.address]))
            item.addChild(QtGui.QTreeWidgetItem(["Joined", "Yes" if device.joined else "No"]))

        # Expand all items in the tree view.
        self._tree_view.expandToDepth(0)

    def _refresh(self):
        """
        Refresh the status of the ground station and the vehicles.
        """

        self._refresh_ground_station()
        self._refresh_vehicles()

    def _refresh_ground_station(self):
        """
        Refresh the status of the ground station.
        """

        identity = self._controller.rf_sensor.get_identity()

        ground_station = self._devices[0]
        ground_station.address = identity["address"]
        ground_station.joined = identity["joined"]

        self._tree_view.clear()
        self._fill()

    def _check_discover(self):
        if self._updated:
            self._tree_view.clear()
            self._fill()
            self._updated = False
            if self._timer is not None and all(device.joined for device in self._devices):
                self._timer.stop()
                self._timer = None

    def _refresh_vehicles(self):
        """
        Refresh the status of the vehicles.
        """

        self._controller.rf_sensor.discover(self._refresh_vehicle)

        self._timer = QtCore.QTimer()
        self._timer.setInterval(self._discover_interval * 1000)
        self._timer.setSingleShot(False)
        self._timer.timeout.connect(self._check_discover)
        self._timer.start()

    def _refresh_vehicle(self, packet):
        """
        Refresh a single vehicle using information from a node discovery `packet`.
        """

        vehicle = self._devices[packet["id"]]
        vehicle.address = packet["address"]
        vehicle.joined = True

        self._updated = True
