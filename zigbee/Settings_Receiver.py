import json
from ..settings import Settings
from Packet import Packet

class Settings_Receiver(object):
    """
    Handler for receiving packets that change settings.
    """

    def __init__(self, environment):
        self._environment = environment
        self._arguments = self._environment.get_arguments()
        self._rf_sensor = self._environment.get_rf_sensor()
        self._thread_manager = self._environment.thread_manager
        self._new_settings = {}

        self._environment.add_packet_action("setting_clear", self._clear)
        self._environment.add_packet_action("setting_add", self._add)
        self._environment.add_packet_action("setting_done", self._done)

    def _cleanup(self):
        Settings.settings_files = {}
        self._arguments.groups = {}
        self._new_settings = {}

    def _send_ack(self, index=-1):
        packet = Packet()
        packet.set("specification", "setting_ack")
        packet.set("next_index", index + 1)
        packet.set("sensor_id", self._rf_sensor.id)

        self._rf_sensor.enqueue(packet, to=0)

    def _clear(self, packet):
        # Ignore packets that are not meant for us.
        if packet.get("to_id") != self._rf_sensor.id:
            return

        self._cleanup()
        self._send_ack()

    def _add(self, packet):
        # Ignore packets that are not meant for us.
        if packet.get("to_id") != self._rf_sensor.id:
            return

        index = packet.get("index")
        key = packet.get("key")
        value = packet.get("value")

        self._new_settings[key] = value

        self._send_ack(index)

    def _done(self, packet):
        # Ignore packets that are not meant for us.
        if packet.get("to_id") != self._rf_sensor.id:
            return

        with open(self._arguments.settings_file, 'w') as settings_file:
            json.dump(self._new_settings, settings_file, indent=4, sort_keys=True)

        # Clean up cached settings and stop the program so that we can restart 
        # it with the new settings.
        self._cleanup()
        self._thread_manager.interrupt(self._rf_sensor.thread_name)
