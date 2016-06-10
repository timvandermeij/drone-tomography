import json
import struct
import zlib

class Packet(object):
    # Packet type specifications loaded from the JSON file.
    # The specifications are cached between packets.
    _specifications = None

    def __init__(self):
        """
        Initialize the packet with an empty contents key-value store.
        All packets must adhere to a fixed specification. The specifications
        for all available packet types are listed in the settings JSON file.
        """

        if self._specifications is None:
            with open("zigbee/specifications.json") as specifications_file:
                self._specifications = json.load(specifications_file)

        self._private = True
        self._contents = {}
        self._object_types = {
            bool: "?",
            int: "i",
            float: "d",
            str: "$"
        }

    def set(self, key, value):
        """
        Set a key and value in the contents key-value store.
        """

        self._contents[key] = value
        if key == "specification" and value in self._specifications:
            specification = self._specifications[value]
            self._private = specification[0]["private"]

    def unset(self, key):
        """
        Unset a key in the contents key-value store.
        """

        if key in self._contents:
            self._contents.pop(key)

    def get(self, key):
        """
        Get the value of a key in the contents key-value store.
        """

        if key in self._contents:
            return self._contents[key]

        return None

    def get_all(self):
        """
        Get all keys and values in the contents key-value store.
        """

        return self._contents

    def get_dump(self):
        """
        Get all values in the contents key-value store and return them
        in a list format for inclusion in a dump file. Such a list contains
        the values of the RSSI ground station packet format (in order).
        """

        specification_name = self.get("specification")
        if specification_name != "rssi_ground_station":
            raise ValueError("Dumps can only be generated for RSSI ground station packets")

        dump = []
        specification = self._specifications[specification_name]
        for field in specification:
            if field["name"] == "id":
                continue

            value = self.get(field["name"])
            dump.append(value)

        return dump

    def set_dump(self, dump):
        """
        Set the values in the contents key-values store by reading the RSSI
        ground station packet fields in order and taking the corresponding
        value from the list in the `dump` parameter.
        """

        specification_name = self.get("specification")
        if specification_name != "rssi_ground_station":
            raise ValueError("Dumps can only be imported for RSSI ground station packets")

        self.set("sensor_id", dump[0])
        self.set("from_latitude", dump[1])
        self.set("from_longitude", dump[2])
        self.set("from_valid", dump[3])
        self.set("to_latitude", dump[4])
        self.set("to_longitude", dump[5])
        self.set("to_valid", dump[6])
        self.set("rssi", dump[7])

    def serialize(self):
        """
        Serialize a contents dictionary as a single byte-encoded string.
        After making sure that the dictionary adheres to the provided
        specification, we process the fields in the same order as in
        the specification.

        The specifications are part of a custom developed format for these
        byte-encoded strings. The first byte is always the specification
        identifier, which in the settings JSON can be found as the
        'value' key. The remaining bytes are added in order according to
        the specification. For instance, if the specification has two fields
        that are both doubles, then 16 additional bytes will be added.
        """

        # Verify that the specification has been provided.
        if "specification" not in self._contents:
            raise KeyError("No specification has been provided")

        specification_name = self._contents["specification"]

        # Verify that the provided specification exists.
        if specification_name not in self._specifications:
            raise KeyError("Unknown specification '{}' has been provided".format(specification_name))

        specification = self._specifications[specification_name]

        # Pack the fields in the same order as in the specification. The
        # order is important as the same order is used to unpack.
        # Verify that all fields in the specification have been provided.
        # In case of fields with a value (usually identifier fields), instead
        # use the provided value.
        packed_message = ""
        for field in specification:
            if "value" in field:
                value = field["value"]
            elif field["name"] in self._contents:
                value = self._contents[field["name"]]
            else:
                raise KeyError("Unable to serialize packet with specification '{}': Field '{}' has not been provided.".format(specification_name, field["name"]))

            try:
                packed_message += self._pack_field(field["format"], value)
            except struct.error as e:
                raise ValueError("Unable to serialize packet with specification '{}': struct error for field '{}': {}".format(specification_name, field["name"], e.message))

        return packed_message

    def _pack_field(self, format, value):
        if format == "$":
            # Special string format: pack the full length of the string. Track 
            # the length with one byte since the length should never be more 
            # than the packet length.
            length = len(value)
            contents = struct.pack("B", length)
            contents += struct.pack("{}s".format(length), value)
        elif format == "@":
            # Special object format: determine the type of the value. If it is 
            # something struct can handle, use it and track which type we used 
            # to pack. Otherwise, serialize with json and compress with zlib. 
            # Track the final length in one byte since the length should never 
            # be more than the packet length. Also track whether it is a packed 
            # type or a JSON-serialized one.
            object_type = type(value)
            if object_type in self._object_types:
                object_format = self._object_types[object_type]
                contents = struct.pack("?", True)
                contents += struct.pack("B", ord(object_format))
                contents += self._pack_field(object_format, value)
            else:
                compressed_data = zlib.compress(json.dumps(value))
                contents = struct.pack("?", False)
                contents += struct.pack("B", len(compressed_data))
                contents += compressed_data
        else:
            contents = struct.pack(format, value)

        return contents

    def unserialize(self, contents):
        """
        Unserialize a given byte-encoded string as a contents dictionary.
        Essentially we reverse the serialization process by first unpacking
        the specification identifier byte. Using that we identify the
        used specification for the rest of the message. We unpack each
        field as provided in the specification in order. This is possible
        because the specification contains the number of bytes required
        per field, allowing us to jump through the byte-encoded string
        using an offset.
        """

        # Unpack the specification identifier.
        specification_id, offset = self._read_packed("B", contents, 0)

        # Fetch the specification belonging to the found identifier.
        specification = None
        specification_name = ""
        for name, fields in self._specifications.iteritems():
            if fields[0]["value"] == specification_id:
                specification = fields
                specification_name = name
                break

        if specification is None:
            raise KeyError("Invalid specification {} has been provided".format(specification_id))

        # Loop through all fields in the specification that do not have
        # a fixed value (in order). Using the format of the field, we
        # can unpack the right part of the byte-encoded string. The offset
        # is used to continue from the last read part of the string.
        self._contents["specification"] = specification_name
        self._private = specification[0]["private"]
        for field in specification:
            if "value" in field:
                continue

            name = field["name"]
            format = field["format"]
            try:
                data, offset = self._read_format(format, contents, offset)
            except struct.error as e:
                raise ValueError("Unable to unserialize packet with specification '{}': struct error for field '{}' at offset {}: {}".format(specification_name, name, offset, e.message))

            self._contents[name] = data

    def _read_format(self, format, contents, offset):
        if format == "$":
            length, offset = self._read_packed("B", contents, offset)

            str_format = "{}s".format(length)
            data, offset = self._read_packed(str_format, contents, offset)
        elif format == "@":
            is_packed, offset = self._read_packed("?", contents, offset)
            if is_packed:
                object_format, offset = self._read_packed("B", contents, offset)
                data, offset = self._read_format(chr(object_format), contents,
                                                 offset)
            else:
                length, offset = self._read_packed("B", contents, offset)
                data_format = "{}s".format(length)

                compressed, offset = self._read_packed(data_format, contents,
                                                       offset)

                data = json.loads(zlib.decompress(compressed))
        else:
            data, offset = self._read_packed(format, contents, offset)

        return data, offset

    def _read_packed(self, format, contents, offset):
        data = struct.unpack_from(format, contents, offset)[0]
        offset += struct.calcsize(format)

        return data, offset

    def is_private(self):
        """
        Return if the packet is private, indicating that it belongs to
        internal code and cannot be enqueued.
        """

        return self._private
