from functools import partial
from PyQt4 import QtGui, QtCore
from ..zigbee.Packet import Packet

class Control_Panel_RF_Sensor_Sender(object):
    """
    Handler for sending packets to the RF sensors on the vehicles.
    """

    def __init__(self, controller, data, total, configuration):
        self._controller = controller
        self._name = configuration["name"]

        self._clear_message = configuration["clear_message"]
        self._add_callback = configuration["add_callback"]
        self._done_message = configuration["done_message"]
        self._ack_message = configuration["ack_message"]

        self._max_retries = configuration["max_retries"]
        self._retry_interval = configuration["retry_interval"]

        self._labels = dict([(vehicle, "") for vehicle in data])

        self._retry_counts = dict([(vehicle, self._max_retries) for vehicle in data])
        self._indexes = dict([(vehicle, -1) for vehicle in data])

        self._timers = {}

        self._data = data
        self._total = total

        self._progress = QtGui.QProgressDialog(self._controller.central_widget)
        self._progress.setMinimum(0)
        self._progress.setMaximum(self._total)
        self._progress.setWindowModality(QtCore.Qt.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.setCancelButtonText("Cancel")
        self._progress.canceled.connect(self._cancel)
        self._progress.setWindowTitle("Sending {}s".format(self._name))
        self._progress.setLabelText("Initializing...")

    def connect_accepted(self, callback):
        self._progress.accepted.connect(callback)

    def start(self):
        self._controller.add_packet_callback(self._ack_message,
                                             self._receive_ack)

        # Create a progress dialog and send the data to the vehicles.
        self._progress.open()

        for vehicle in self._data:
            timer = QtCore.QTimer()
            timer.setInterval(self._retry_interval * 1000)
            timer.setSingleShot(True)
            # Bind timeout signal to retry for the current vehicle.
            timer.timeout.connect(partial(self._retry, vehicle))
            self._timers[vehicle] = timer

        for vehicle in self._data:
            self._send_clear(vehicle)

    def _send_clear(self, vehicle):
        packet = Packet()
        packet.set("specification", self._clear_message)
        packet.set("to_id", vehicle)

        self._controller.rf_sensor.enqueue(packet, to=vehicle)

        self._set_label(vehicle, "Clearing old {}s".format(self._name))
        self._timers[vehicle].start()

    def _is_done(self, vehicle):
        return len(self._data[vehicle]) <= self._indexes[vehicle]

    def _send_one(self, vehicle):
        if self._is_done(vehicle):
            # Enqueue a packet indicating that sending data to this vehicle is 
            # done.
            packet = Packet()
            packet.set("specification", self._done_message)
            packet.set("to_id", vehicle)
            self._controller.rf_sensor.enqueue(packet, to=vehicle)

            self._update_value()
            if all(self._is_done(vehicle) for vehicle in self._indexes):
                self._progress.accept()

            return

        index = self._indexes[vehicle]
        data = self._data[vehicle][index]

        packet = self._add_callback(vehicle, index, data)

        self._controller.rf_sensor.enqueue(packet, to=vehicle)

        self._set_label(vehicle, "Sending {} #{}: {}".format(self._name, index+1, data))
        self._timers[vehicle].start()

    def _receive_ack(self, packet):
        vehicle = packet.get("sensor_id")
        index = packet.get("next_index")

        if vehicle not in self._timers:
            return

        self._indexes[vehicle] = index
        self._retry_counts[vehicle] = self._max_retries + 1

    def _retry(self, vehicle):
        self._retry_counts[vehicle] -= 1
        if self._retry_counts[vehicle] > 0:
            if self._indexes[vehicle] == -1:
                self._send_clear(vehicle)
            else:
                self._send_one(vehicle)
        else:
            # Maximum retry attempts reached, cancel the send action
            if self._indexes[vehicle] == -1:
                send = "clearing {}s".format(self._name)
            else:
                send = "{} #{}".format(self._name, self._indexes[vehicle])
            self._cancel("Vehicle {}: Maximum retry attempts for {} reached".format(vehicle, send))

    def _set_label(self, vehicle, text):
        self._labels[vehicle] = text
        self._update_labels()
        self._update_value()

    def _update_labels(self):
        labels = []
        for vehicle in sorted(self._labels.iterkeys()):
            label = self._labels[vehicle]
            if self._retry_counts[vehicle] < self._max_retries:
                retry = " ({} attempts remaining)".format(self._retry_counts[vehicle])
            else:
                retry = ""

            labels.append("Vehicle {}: {}{}".format(vehicle, label, retry))

        self._progress.setLabelText("\n".join(labels))

    def _update_value(self):
        self._progress.setValue(max(0, min(self._total, sum(self._indexes.values()))))

    def _cancel(self, message=None):
        self._controller.remove_packet_callback(self._ack_message)

        for timer in self._timers.values():
            timer.stop()

        if self._progress is not None:
            self._progress.cancel()
            self._progress.deleteLater()

        if message is not None:
            QtGui.QMessageBox.critical(self._controller.central_widget,
                                       "Sending failed", message)
