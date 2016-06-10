import json
import os
from PyQt4 import QtGui
from Control_Panel_RF_Sensor_Sender import Control_Panel_RF_Sensor_Sender
from Control_Panel_View import Control_Panel_View
from Control_Panel_Waypoints_Widgets import WaypointsTableWidget
from ..zigbee.Packet import Packet

class Control_Panel_Waypoints_View(Control_Panel_View):
    def __init__(self, controller, settings):
        super(Control_Panel_Waypoints_View, self).__init__(controller, settings)

        self._max_retries = self._settings.get("waypoints_max_retries")
        self._retry_interval = self._settings.get("waypoints_retry_interval")

        self._vehicle_labels = []
        self._tables = []
        self._column_labels = ["north", "east", "altitude", "wait for vehicle"]
        # Default values that are used when exporting/importing tables.
        # We initially require data for the north/east column, but the altitude 
        # and wait ID can be left out.
        self._column_defaults = (None, None, 0.0, 0)

        self._listWidget = None
        self._stackedLayout = None

    def load(self, data):
        self._listWidget = QtGui.QListWidget()
        self._stackedLayout = QtGui.QStackedLayout()

        for vehicle in xrange(1, self._controller.rf_sensor.number_of_sensors + 1):
            # Create the list item for the vehicle.
            self._listWidget.addItem("Waypoints for vehicle {}".format(vehicle))

            # Create the table for the vehicle.
            table = WaypointsTableWidget(self._column_labels, self._column_defaults)

            self._tables.append(table)
            self._stackedLayout.addWidget(table)

        if "waypoints" in data:
            try:
                waypoints = self._convert_waypoints(data["waypoints"])
                self._import_waypoints(waypoints, from_json=False)
            except ValueError:
                return

    def save(self):
        return {
            "waypoints": self._export_waypoints(repeat=False, errors=False)[0]
        }

    def show(self):
        """
        Show the waypoints view.
        """

        self._add_menu_bar()

        self._listWidget.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Expanding)
        self._listWidget.setCurrentRow(0)
        self._listWidget.currentRowChanged.connect(self._stackedLayout.setCurrentIndex)

        # Create the buttons for adding new rows and sending the waypoints.
        add_row_button = QtGui.QPushButton("Add row")
        add_row_button.clicked.connect(self._add_row)
        import_button = QtGui.QPushButton("Import")
        import_button.clicked.connect(self._import)
        export_button = QtGui.QPushButton("Export")
        export_button.clicked.connect(self._export)
        send_button = QtGui.QPushButton("Send")
        send_button.clicked.connect(self._send)

        # Create the layout and add the widgets.
        hbox_stacks = QtGui.QHBoxLayout()
        hbox_stacks.addWidget(self._listWidget)
        hbox_stacks.addLayout(self._stackedLayout)

        hbox_buttons = QtGui.QHBoxLayout()
        hbox_buttons.addWidget(add_row_button)
        hbox_buttons.addStretch(1)
        hbox_buttons.addWidget(import_button)
        hbox_buttons.addWidget(export_button)
        hbox_buttons.addStretch(1)
        hbox_buttons.addWidget(send_button)

        vbox = QtGui.QVBoxLayout(self._controller.central_widget)
        vbox.addLayout(hbox_stacks)
        vbox.addLayout(hbox_buttons)

    def _add_row(self):
        """
        Add a row to all tables at the same time.
        """

        for table in self._tables:
            table.insertRow(table.rowCount())

    def _format_row_data(self, vehicle, table, row, previous, repeat=True, errors=True):
        """
        Format a single row from a waypoints table for exporting.

        This method grabs the cells from the given `table` at row number `row`
        for the given vehicle `vehicle`, given that the data from the previous
        row is given in `previous`. If there is no previous row, then this is
        equal to the column defaults.

        Can raise a `ValueError` for missing or invalid cell data.
        """

        data = []
        for col in range(len(self._column_labels)):
            item = table.item(row, col)
            # Handle unchanged columns (no item widget) or empty columns (text 
            # contents equals to empty string)
            if item is None or item.text() == "":
                data.append(None)
            else:
                data.append(item.text())

        if all(item is None for item in data) and previous == self._column_defaults:
            # If the first table row is completely empty, then silently ignore 
            # this row.
            return []

        if errors:
            pair = zip(data, previous)
            if any(val is None and prev is None for val, prev in pair):
                # If a column has no data and no previous data either, then we 
                # have missing information.
                raise ValueError("Missing coordinates for vehicle {}, row #{} and no previous waypoint".format(vehicle, row + 1))

        for i, col in enumerate(self._column_labels):
            if data[i] is None:
                # If a table cell is empty, use the previous waypoint's 
                # coordinates for the current waypoint.
                data[i] = previous[i] if repeat else self._column_defaults[i]
            else:
                try:
                    data[i] = self._cast_cell(i, data[i])
                except ValueError:
                    if errors:
                        raise ValueError("Invalid value for vehicle {}, row #{}, column '{}': '{}'".format(vehicle, row + 1, col, data[i]))

        return data

    def _cast_cell(self, col, text):
        """
        Change the text from a cell in column `col` to correct type.

        Returns the casted value. Raises a `ValueError` if the text cannot be
        casted to the appropriate value.
        """

        if self._column_defaults[col] is not None:
            type_cast = type(self._column_defaults[col])
        else:
            type_cast = float

        return type_cast(text)

    def _export_waypoints(self, repeat=True, errors=True):
        """
        Create a dictonary containing lists of waypoints (tuples) per vehicle
        from the current contents of the tables.

        When `repeat` is enabled, the output for rows with empty column is
        augmented with data from previous rows. This is perfect for exporting
        to somewhat readable JSON files and the actual sending mechanisms, but
        can be disabled for internal storage since `_import_waypoint` handles
        data that is default differently than repeated data.

        When `errors` is enabled, columns that have missing first data when
        they are required raise a `ValueError`, and invalid values do as well.
        This can also be disabled for internal storage.
        """

        waypoints = {}
        total = 0
        for index, table in enumerate(self._tables):
            # Keep vehicle index as string here since send and save make use of 
            # integer indices, while JSON export will automatically convert 
            # them to string keys.
            vehicle = index + 1
            previous = self._column_defaults
            for row in range(table.rowCount()):
                data = self._format_row_data(vehicle, table, row, previous,
                                             repeat=repeat, errors=errors)

                if not data:
                    continue

                if vehicle not in waypoints:
                    waypoints[vehicle] = [tuple(data)]
                else:
                    waypoints[vehicle].append(tuple(data))

                total += 1
                previous = tuple(data)

        return waypoints, total

    def _convert_waypoints(self, waypoints):
        """
        Convert an imported object containing waypoints to a dictionary of lists
        of waypoints (tuples) for each vehicle.

        If the `waypoints` objects is already such a dictionary, it is left
        intact. If it is a list, then it is assumed that it has lists of sensor
        pairs (lists of lists). This is mostly for compatibility with output
        from a planning algorithm.

        If the waypoints could not be converted, then a `ValueError` is raised.
        """

        if isinstance(waypoints, list):
            try:
                waypoints = {
                    1: [sensor_pairs[0] for sensor_pairs in waypoints],
                    2: [sensor_pairs[1] for sensor_pairs in waypoints]
                }
            except IndexError:
                raise ValueError("JSON list must contain sensor pairs")
        elif not isinstance(waypoints, dict):
            raise ValueError("Waypoints must be a JSON list or array")

        return waypoints

    def _import_waypoints(self, waypoints, from_json=True):
        """
        Populate the tables from a dictionary of lists of waypoints (tuples)
        for each vehicle.

        When `from_json` is enabled, consider the dictionary to be loaded from
        a JSON file, which has strings as vehicle index keys.
        """

        for index, table in enumerate(self._tables):
            # Allow either string or numeric indices depending on import source
            vehicle = str(index + 1) if from_json else index + 1
            if vehicle not in waypoints:
                continue

            table.removeRows()
            for row, waypoint in enumerate(waypoints[vehicle]):
                table.insertRow(row)
                for col in range(len(self._column_labels)):
                    if col >= len(waypoint):
                        if self._column_defaults[col] is None:
                            # Data is required for this column, but it is not 
                            # provided.
                            raise ValueError("Row #{} has missing information for column '{}'".format(row + 1, self._column_labels[col]))

                        break

                    if waypoint[col] != self._column_defaults[col]:
                        item = str(waypoint[col])
                        table.setItem(row, col, QtGui.QTableWidgetItem(item))

    def _import(self):
        """
        Import waypoints from a JSON file that was exported from the waypoints
        view or from the planning algorithm.
        """

        fn = QtGui.QFileDialog.getOpenFileName(self._controller.central_widget,
                                               "Import file", os.getcwd(),
                                               "JSON files (*.json)")
        if fn == "":
            return

        try:
            with open(fn, 'r') as import_file:
                waypoints = self._convert_waypoints(json.load(import_file))
        except IOError as e:
            message = "Could not open file '{}': {}".format(fn, e.strerror)
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "File error", message)
            return
        except ValueError as e:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "JSON error", e.message)
            return

        try:
            self._import_waypoints(waypoints, from_json=True)
        except ValueError as e:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "Waypoint incorrect", e.message)

    def _export(self):
        """
        Export the waypoints in the tables to a JSON file.
        """

        try:
            waypoints = self._export_waypoints()[0]
        except ValueError as e:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "Waypoint incorrect", e.message)
            return

        fn = QtGui.QFileDialog.getSaveFileName(self._controller.central_widget,
                                               "Export file", os.getcwd(),
                                               "JSON files (*.json)")
        if fn == "":
            return

        try:
            with open(fn, 'w') as export_file:
                json.dump(waypoints, export_file)
        except IOError as e:
            message = "Could not open file '{}': {}".format(fn, e.strerror)
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "File error", message)

    def _send(self):
        """
        Send the waypoints from all tables to the corresponding vehicles.
        """

        try:
            waypoints, total = self._export_waypoints()
        except ValueError as e:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "Waypoint incorrect", e.message)
            return

        if total == 0:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "No waypoints",
                                       "There are no vehicles with waypoints.")
            return

        configuration = {
            "name": "waypoint",
            "clear_message": "waypoint_clear",
            "add_callback": self._make_add_waypoint_packet,
            "done_message": "waypoint_done",
            "ack_message": "waypoint_ack",
            "max_retries": self._max_retries,
            "retry_interval": self._retry_interval
        }
        sender = Control_Panel_RF_Sensor_Sender(self._controller, waypoints, total,
                                                configuration)
        sender.start()

    def _make_add_waypoint_packet(self, vehicle, index, waypoint):
        """
        Create a `Packet` object with the `waypoint_add` specification
        and fill its fields with correct values.

        This is a callback for the `Control_Panel_RF_Sensor_Sender`.
        """

        packet = Packet()
        packet.set("specification", "waypoint_add")
        packet.set("latitude", waypoint[0])
        packet.set("longitude", waypoint[1])
        packet.set("altitude", waypoint[2])
        packet.set("wait_id", int(waypoint[3]))
        packet.set("index", index)
        packet.set("to_id", vehicle)

        return packet
