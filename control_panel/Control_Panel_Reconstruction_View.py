# TODO:
# - Investigate canvas flipping
# - Average measurements of the same link
# - Tweak calibration/ellipse width/singular values/model (based on grid experiments)

# Core imports
import json
import thread
import os

# Qt imports
from PyQt4 import QtGui, QtCore
import pyqtgraph as pg

# matplotlib imports
import matplotlib
matplotlib.use("Qt4Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas

# Other library imports
import numpy as np

# Package imports
from Control_Panel_Settings_Widgets import SettingsTableWidget
from Control_Panel_View import Control_Panel_View
from ..core.Import_Manager import Import_Manager
from ..reconstruction.Coordinator import Coordinator
from ..reconstruction.Dataset_Buffer import Dataset_Buffer
from ..reconstruction.Dump_Buffer import Dump_Buffer
from ..reconstruction.Stream_Buffer import Stream_Buffer

class Graph(object):
    def __init__(self, settings):
        """
        Initialize the graph object.
        """

        self._settings = settings

        # Enable antialiassing and use a transparent background with black text/lines.
        pg.setConfigOptions(antialias=True, background=None, foreground="k")

        # Prepare data structures for the graph.
        self._number_of_sensors = 0
        self._graph = None
        self._graph_curve_points = self._settings.get("reconstruction_curve_points")
        self._graph_curves = []
        self._graph_data = []

    def setup(self, buffer):
        """
        Setup the graph with the number of sensors from the buffer.
        """

        self._number_of_sensors = buffer.number_of_sensors

        # Create the data lists for the graph.
        self._graph_data = [[] for vehicle in range(1, self._number_of_sensors + 1)]

        # Create the curves for the graph.
        color_index = 0
        for vehicle in range(1, self._number_of_sensors + 1):
            index = vehicle - 1

            color = pg.intColor(color_index, hues=len(self._graph_data), maxValue=200)
            color_index += 1

            curve = self._graph.plot()
            curve.setData(self._graph_data[index], pen=pg.mkPen(color, width=1.5))
            self._graph_curves.append(curve)

    def create(self):
        """
        Create the graph.
        """

        if self._graph is not None:
            return self._graph

        self._graph = pg.PlotWidget()
        self._graph.setXRange(0, self._graph_curve_points)
        self._graph.setLabel("left", "RSSI")
        self._graph.setLabel("bottom", "Measurement")

        return self._graph

    def update(self, packet):
        """
        Update the graph with information in `packet`.
        """

        for vehicle in range(1, self._number_of_sensors + 1):
            index = vehicle - 1

            if len(self._graph_data[index]) > self._graph_curve_points:
                self._graph_data[index].pop(0)

            if packet.get("sensor_id") == vehicle:
                self._graph_data[index].append(packet.get("rssi"))

            self._graph_curves[index].setData(self._graph_data[index])

    def clear(self):
        """
        Clear the graph.
        """

        for curve in self._graph_curves:
            curve.clear()

        self._graph_data = []
        self._graph_curves = []

class Table(object):
    def __init__(self):
        """
        Initialize the table object.
        """

        self._table = None

    def create(self):
        """
        Create the table.
        """

        if self._table is not None:
            return self._table

        column_labels = ["Vehicle", "Source location", "Destination location", "RSSI"]

        self._table = QtGui.QTableWidget()
        self._table.setRowCount(0)
        self._table.setColumnCount(len(column_labels))
        self._table.setHorizontalHeaderLabels(column_labels)
        self._table.setEditTriggers(QtGui.QAbstractItemView.NoEditTriggers)

        horizontalHeader = self._table.horizontalHeader()
        for index in range(len(column_labels)):
            horizontalHeader.setResizeMode(index, QtGui.QHeaderView.Stretch)

        return self._table

    def update(self, packet):
        """
        Update the table with information in `packet`.
        """

        # Collect and format the data.
        vehicle = str(packet.get("sensor_id"))
        source_location = "({}, {})".format(packet.get("from_latitude"), packet.get("from_longitude"))
        destination_location = "({}, {})".format(packet.get("to_latitude"), packet.get("to_longitude"))
        rssi = str(packet.get("rssi"))

        # Append a new table row.
        position = self._table.rowCount()
        self._table.insertRow(position)
        self._table.setItem(position, 0, QtGui.QTableWidgetItem(vehicle))
        self._table.setItem(position, 1, QtGui.QTableWidgetItem(source_location))
        self._table.setItem(position, 2, QtGui.QTableWidgetItem(destination_location))
        self._table.setItem(position, 3, QtGui.QTableWidgetItem(rssi))

        # Indicate the validity of the source and destination locations.
        green = QtGui.QColor("#8BD672")
        red = QtGui.QColor("#FA6969")
        self._table.item(position, 1).setBackground(green if packet.get("from_valid") else red)
        self._table.item(position, 2).setBackground(green if packet.get("to_valid") else red)

        # Automatically scroll the table to the bottom.
        self._table.scrollToBottom()

    def clear(self):
        """
        Clear the table.
        """

        for index in reversed(range(self._table.rowCount())):
            self._table.removeRow(index)

class Stream_Recorder(object):
    def __init__(self, controller=None, settings=None):
        """
        Initialize the stream recorder object.

        The stream recorder keeps a copy of every incoming packet when recording mode is
        enabled. When recording is stopped, the captured data is exported to a dump file.
        """

        if controller is None:
            raise ValueError("Controller for the stream recorder has not been provided.")

        if settings is None:
            raise ValueError("Settings for the stream recorder have not been provided.")

        self._controller = controller

        self._number_of_sensors = controller.rf_sensor.number_of_sensors
        self._origin = settings.get("stream_network_origin")
        self._size = settings.get("stream_network_size")

        self._packets = []

    def update(self, packet):
        """
        Update the stream recorder with information in `packet`.
        """

        self._packets.append(packet)

    def export(self):
        """
        Export the packets (along with network information) to a dump file.
        """

        file_name = QtGui.QFileDialog.getSaveFileName(self._controller.central_widget,
                                                      "Export file", os.getcwd(),
                                                      "JSON files (*.json)")

        if file_name == "":
            return

        try:
            with open(file_name, "w") as export_file:
                json.dump({
                    "number_of_sensors": self._number_of_sensors,
                    "origin": self._origin,
                    "size": self._size,
                    "packets": [packet.get_dump() for packet in self._packets]
                }, export_file)
        except IOError as e:
            message = "Could not open file '{}': {}".format(file_name, e.strerror)
            QtGui.QMessageBox.critical(self._controller.central_widget, "File error", message)

class Control_Panel_Reconstruction_View(Control_Panel_View):
    def __init__(self, controller, settings):
        super(Control_Panel_Reconstruction_View, self).__init__(controller, settings)

        self._running = False

        self._axes = None
        self._canvas = None
        self._graph = None
        self._table = None

        self._sources = [
            {
                "title": "Dataset",
                "component": "reconstruction_dataset",
                "buffer": Dataset_Buffer
            },
            {
                "title": "Dump",
                "component": "reconstruction_dump",
                "buffer": Dump_Buffer
            },
            {
                "title": "Stream",
                "component": "reconstruction_stream",
                "buffer": Stream_Buffer
            }
        ]

        self._panels = None
        self._stackedWidget = None
        self._toggle_button = None

        self._source_forms = []
        self._reconstructor_forms = {}

        self._pause_time = self._settings.get("reconstruction_pause_time") * 1000
        self._percentiles = None
        self._interpolation = None
        self._chunk_size = None
        self._cmap = None

        self._coordinator = None
        self._buffer = None
        self._stream_recorder = None
        self._reconstructor = None

        self._previous_pixels = None
        self._chunk_count = 0

        self._import_manager = Import_Manager()

    def show(self):
        """
        Show the reconstruction view.
        """

        self._add_menu_bar()

        # Create the image.
        figure = plt.figure(frameon=False)
        self._axes = figure.add_axes([0, 0, 1, 1])
        self._axes.axis("off")
        self._canvas = FigureCanvas(figure)

        # Create the graph and table.
        self._graph = Graph(self._settings)
        self._table = Table()

        # Create the tab widget.
        tabs = QtGui.QTabWidget()
        tabs.addTab(self._graph.create(), "Graph")
        tabs.addTab(self._table.create(), "Table")

        # Create the panels. These are tabs containing the forms for each input 
        # source (dataset, dump and stream). Additionally, there is a stacked 
        # widget for the reconstructor-specific settings.
        self._panels = QtGui.QTabWidget()
        self._panels.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Expanding)

        self._stackedWidget = QtGui.QStackedWidget()
        self._stackedWidget.setSizePolicy(QtGui.QSizePolicy.Fixed, QtGui.QSizePolicy.Maximum)

        self._source_forms = []
        self._reconstructor_forms = {}

        for source in self._sources:
            form = SettingsTableWidget(self._controller.arguments,
                                       source["component"])

            # Handle changes to the reconstructor combo box selection to show 
            # its settings in the stacked widget.
            reconstructor_box = form.get_value_widget("reconstructor")
            reconstructor_box.currentIndexChanged[QtCore.QString].connect(self._update_reconstructor)

            # Register the source settings widget.
            self._panels.addTab(form, source["title"])
            self._source_forms.append(form)

        # Update the stacked widget when switching tabs in the panel, and 
        # ensure the first stacked widget is loaded.
        self._panels.currentChanged.connect(self._update_form)
        self._update_form(0)

        # Create the toggle button (using the stopped state as default).
        self._toggle_button = QtGui.QPushButton(QtGui.QIcon("assets/start.png"), "Start")
        self._toggle_button.clicked.connect(self._toggle)

        # Create the layout and add the widgets.
        vbox_left = QtGui.QVBoxLayout()
        vbox_left.addWidget(self._panels)
        vbox_left.addWidget(self._stackedWidget)
        vbox_left.addWidget(self._toggle_button)

        vbox_right = QtGui.QVBoxLayout()
        vbox_right.addWidget(self._canvas)
        vbox_right.addStretch(1)
        vbox_right.addWidget(tabs)

        hbox = QtGui.QHBoxLayout(self._controller.central_widget)
        hbox.addLayout(vbox_left)
        hbox.addLayout(vbox_right)

    def _toggle(self):
        """
        Toggle the state of the reconstruction (start or stop).
        """

        self._running = not self._running

        if self._running:
            self._toggle_button.setIcon(QtGui.QIcon("assets/stop.png"))
            self._toggle_button.setText("Stop")

            self._start()
        else:
            self._toggle_button.setIcon(QtGui.QIcon("assets/start.png"))
            self._toggle_button.setText("Start")

    def _update_form(self, index):
        """
        Update the stacked widget with the reconstructor settings based
        on the reconstructor combo box in the current source form.
        """

        form = self._source_forms[index]

        reconstructor_box = form.get_value_widget("reconstructor")
        self._update_reconstructor(reconstructor_box.currentText())

    def _update_reconstructor_policy(self, policy):
        """
        Adjust the size of the stacked widget based on the given `policy`.
        """

        currentWidget = self._stackedWidget.currentWidget()
        if currentWidget is not None:
            currentWidget.setSizePolicy(policy, policy)
            currentWidget.adjustSize()
            self._stackedWidget.adjustSize()

    def _update_reconstructor(self, text):
        """
        Update the stacked widget with the reconstructor settings based on
        the `text` in the reconstructor combo box in the current source form.
        """

        parts = str(text).split(' ')[:-1]
        name = '_'.join(parts).lower()
        component = "reconstruction_{}".format(name)

        # The stacked widget may no longer need the current size.
        self._update_reconstructor_policy(QtGui.QSizePolicy.Ignored)

        if component in self._reconstructor_forms:
            # The selected reconstructor's settings have been shown before, so 
            # only switch to it and update the size.
            self._stackedWidget.setCurrentWidget(self._reconstructor_forms[component])
            self._update_reconstructor_policy(QtGui.QSizePolicy.Expanding)
            return

        # Retrieve a widget for the reconstructor form.
        form = self._get_reconstructor_form(component)

        # Register the new reconstructor form and show it in correct size.
        self._reconstructor_forms[component] = form
        index = self._stackedWidget.addWidget(form)
        self._stackedWidget.setCurrentIndex(index)
        self._update_reconstructor_policy(QtGui.QSizePolicy.Expanding)

    def _get_reconstructor_form(self, component):
        """
        Create a settings widget for a reconstructor.
        If the reconstructor class has a settings name `component` with
        the format "reconstruction_*" without the _Reconstructor trail,
        then a `SettingsTableWidget` is returned. Otherwise, an empty
        `QWidget` is returned.
        """

        try:
            self._controller.arguments.get_settings(component)
        except KeyError:
            return QtGui.QWidget()
        else:
            return SettingsTableWidget(self._controller.arguments, component)

    def _set_form_settings(self, form):
        """
        Retrieve and update settings from a settings form widget.

        If an error occurs, it is displayed and the method returns `None`
        instead of the `Settings` object.
        """

        settings = form.get_settings()
        try:
            values, disallowed = form.get_all_values()
            form.check_disallowed(disallowed)
        except ValueError as e:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "Invalid value", e.message)
            return None

        for key, value in values.iteritems():
            try:
                settings.set(key, value)
            except ValueError as e:
                QtGui.QMessageBox.critical(self._controller.central_widget,
                                           "Settings error", e.message)
                return None

        return settings

    def _start(self):
        """
        Start the reconstruction process.
        """

        # Determine the current panel and update the settings from the form.
        panel_id = self._panels.currentIndex()
        source = self._sources[panel_id]
        source_form = self._source_forms[panel_id]

        settings = self._set_form_settings(source_form)
        if settings is None:
            self._toggle()
            return

        # Update reconstructor settings, if one that has settings is selected.
        reconstructor_form = self._stackedWidget.currentWidget()
        if isinstance(reconstructor_form, SettingsTableWidget):
            reconstructor_settings = self._set_form_settings(reconstructor_form)
            if reconstructor_settings is None:
                self._toggle()
                return

        # Fetch the settings for the reconstruction.
        self._percentiles = settings.get("percentiles")
        self._interpolation = settings.get("interpolation")
        self._chunk_size = settings.get("chunk_size")

        # Prepare the color map for the reconstruction.
        cmap = plt.get_cmap(settings.get("cmap"))
        self._cmap = np.array([cmap(color) for color in range(256)]) * 255

        # Create the buffer and reconstructor.
        try:
            self._create_buffer(source, settings)
            self._create_reconstructor(settings)
        except IOError as e:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "File error",
                                       "Could not open file '{}': {}".format(e.filename, e.strerror))
            self._toggle()
            return
        except StandardError as e:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "Initialization error", e.message)
            self._toggle()
            return

        # Create the coordinator.
        self._coordinator = Coordinator(self._controller.arguments,
                                        self._buffer)

        # Clear the graph and table and setup the graph.
        self._graph.clear()
        self._graph.setup(self._buffer)
        self._table.clear()

        # Clear the image.
        self._axes.cla()
        self._axes.axis("off")
        self._canvas.draw()

        # Execute the reconstruction and visualization.
        self._chunk_count = 0
        self._loop()

    def _create_buffer(self, source, settings):
        """
        Create the buffer for the reconstruction process (depending on the data source).
        """

        buffer_class = source["buffer"]
        self._buffer = buffer_class(settings)

        if isinstance(self._buffer, Stream_Buffer):
            self._buffer.register_rf_sensor(self._controller.rf_sensor)

            if settings.get("stream_record") or settings.get("stream_calibrate"):
                # Create a stream recorder instance to record all incoming 
                # packets. The existence of this object is enough to let the 
                # loop handle the recording process.
                self._stream_recorder = Stream_Recorder(self._controller, settings)

    def _create_reconstructor(self, settings):
        """
        Create the reconstructor for the reconstruction process.
        """

        reconstructor = settings.get("reconstructor")
        reconstructor_class = self._import_manager.load_class(reconstructor,
                                                              relative_module="reconstruction")

        self._reconstructor = reconstructor_class(self._controller.arguments)

    def _loop(self):
        """
        Execute the reconstruction loop.
        """

        # Stop if the stop button has been pressed.
        if not self._running:
            if self._stream_recorder is not None:
                self._stream_recorder.export()
                self._stream_recorder = None

            return

        # If no packets are available yet, wait for them to arrive.
        if self._buffer.count() == 0:
            QtCore.QTimer.singleShot(self._pause_time, self._loop)
            return

        packet, calibrated_rssi = self._buffer.get()

        # Update the graph, table and stream recorder (if applicable) with the packet.
        self._graph.update(packet)
        self._table.update(packet)
        if self._stream_recorder is not None:
            self._stream_recorder.update(packet)

        # Only use packets with valid source and destination locations.
        if not packet.get("from_valid") or not packet.get("to_valid"):
            QtCore.QTimer.singleShot(self._pause_time, self._loop)
            return

        # We attempt to reconstruct an image when the coordinator successfully
        # updated the weight matrix and the RSSI vector and when we have obtained
        # the required number of measurements to fill a chunk.
        self._previous_pixels = None
        if self._coordinator.update(packet, calibrated_rssi):
            self._chunk_count += 1
            if self._chunk_count >= self._chunk_size:
                self._chunk_count = 0

                thread.start_new_thread(self._render, ())

        QtCore.QTimer.singleShot(self._pause_time, self._loop)

    def _render(self):
        """
        Render and draw the image using Matplotlib. This runs in a separate thread.
        """

        try:
            # Get the list of pixel values from the reconstructor.
            pixels = self._reconstructor.execute(self._coordinator.get_weight_matrix(),
                                                 self._coordinator.get_rssi_vector(),
                                                 buffer=self._buffer, guess=self._previous_pixels)
            self._previous_pixels = pixels

            # Reshape the list of pixel values to form the image. Smoothen the image
            # by suppressing pixel values that do not correspond to high attenuation.
            pixels = pixels.reshape(self._buffer.size)
            levels = [np.percentile(pixels, self._percentiles[0]), np.percentile(pixels, self._percentiles[1])]
            image = pg.functions.makeRGBA(pixels, levels=levels, lut=self._cmap)[0]

            # Draw the image onto the canvas and apply interpolation.
            self._axes.axis("off")
            self._axes.imshow(image, origin="lower", interpolation=self._interpolation)
            self._canvas.draw()

            # Delete the image from memory now that it is drawn.
            self._axes.cla()
        except StandardError:
            # There is not enough data yet for the reconstruction algorithm.
            pass
