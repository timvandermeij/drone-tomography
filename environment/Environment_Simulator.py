from Environment import Environment
from VRMLLoader import VRMLLoader

class Environment_Simulator(Environment):
    """
    Simulated environment including objects around the vehicle
    and potentially the vehicle itself. This allows us to simulate
    a mission without many dependencies on ArduPilot.
    """

    _sensor_class = "Distance_Sensor_Simulator"

    def __init__(self, vehicle, geometry, arguments,
                 import_manager, thread_manager, usb_manager):
        super(Environment_Simulator, self).__init__(vehicle, geometry,
                                                    arguments, import_manager,
                                                    thread_manager, usb_manager)

        self.has_location_check = False
        self.old_location = None

        scenefile = self.settings.get("scenefile")
        translation = self.settings.get("translation")

        self.vehicle.home_location = self.get_location(*translation)

        if scenefile is not None:
            if self.settings.get("location_check"):
                self.set_location_check()

            loader = VRMLLoader(self, scenefile, translation)
            self.objects = loader.get_objects()
            return

        # Use hardcoded objects for testing
        l1 = self.get_location(100, 0, 10)
        l2 = self.get_location(0, 100, 10)
        l3 = self.get_location(-100, 0, 10)
        l4 = self.get_location(0, -100, 10)

        # Simplify function call
        get_location_meters = self.geometry.get_location_meters
        self.objects = [
            {
                'center': get_location_meters(self.vehicle.location, 40, -10),
                'radius': 2.5,
            },
            (get_location_meters(l1, 40, -40), get_location_meters(l1, 40, 40),
             get_location_meters(l1, -40, 40), get_location_meters(l1, -40, -40)
            ),
            (get_location_meters(l2, 40, -40), get_location_meters(l2, 40, 40),
             get_location_meters(l2, -40, 40), get_location_meters(l2, -40, -40)
            ),
            (get_location_meters(l3, 40, -40), get_location_meters(l3, 40, 40),
             get_location_meters(l3, -40, 40), get_location_meters(l3, -40, -40)
            ),
            (get_location_meters(l4, 40, -40), get_location_meters(l4, 40, 40),
             get_location_meters(l4, -40, 40), get_location_meters(l4, -40, -40)
            )
        ]

    def get_objects(self):
        return self.objects

    def set_location_check(self):
        self.vehicle.add_attribute_listener('location.local_frame',
                                            self.check_location)
        self.has_location_check = True

    def remove_location_check(self):
        self.vehicle.remove_attribute_listener('location.local_frame',
                                               self.check_location)
        self.has_location_check = False
        self.old_location = None

    def check_location(self, vehicle, attribute, new_location):
        if self.old_location is not None:
            for obj in self.objects:
                if isinstance(obj, list):
                    for face in obj:
                        factor = self.geometry.get_plane_intersection(face, self.old_location, new_location)[0]
                        if 0 <= factor <= 1:
                            raise RuntimeError("Flew through an object")

        self.old_location = new_location
