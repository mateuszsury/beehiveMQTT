"""
MQTT 3.1.1 packet parser and serializer for BeehiveMQTT broker.

This module handles all MQTT packet types according to the MQTT 3.1.1 specification.
Optimized for MicroPython on ESP32 with minimal memory allocations.

Protocol Reference: http://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html
"""

import struct
from .errors import MQTTProtocolError
from .utils import decode_utf8_string, encode_utf8_string, encode_remaining_length

# MQTT packet type constants
CONNECT = 1
CONNACK = 2
PUBLISH = 3
PUBACK = 4
PUBREC = 5
PUBREL = 6
PUBCOMP = 7
SUBSCRIBE = 8
SUBACK = 9
UNSUBSCRIBE = 10
UNSUBACK = 11
PINGREQ = 12
PINGRESP = 13
DISCONNECT = 14

# Pre-allocated response packets for efficiency
PINGRESP_BYTES = bytes([0xD0, 0x00])

# CONNACK return codes
CONNACK_ACCEPTED = 0
CONNACK_REFUSED_PROTOCOL = 1
CONNACK_REFUSED_IDENTIFIER = 2
CONNACK_REFUSED_SERVER = 3
CONNACK_REFUSED_CREDENTIALS = 4
CONNACK_REFUSED_NOT_AUTHORIZED = 5


class ConnectData:
    """Parsed CONNECT packet data."""
    __slots__ = (
        'protocol_name',
        'protocol_level',
        'clean_session',
        'keep_alive',
        'client_id',
        'will_topic',
        'will_message',
        'will_qos',
        'will_retain',
        'username',
        'password',
        'has_will',
        'has_username',
        'has_password'
    )

    def __init__(self):
        self.protocol_name = None
        self.protocol_level = None
        self.clean_session = False
        self.keep_alive = 0
        self.client_id = None
        self.will_topic = None
        self.will_message = None
        self.will_qos = 0
        self.will_retain = False
        self.username = None
        self.password = None
        self.has_will = False
        self.has_username = False
        self.has_password = False


class PublishData:
    """Parsed PUBLISH packet data."""
    __slots__ = ('topic', 'payload', 'qos', 'retain', 'dup', 'packet_id')

    def __init__(self):
        self.topic = None
        self.payload = None
        self.qos = 0
        self.retain = False
        self.dup = False
        self.packet_id = None


class SubscribeData:
    """Parsed SUBSCRIBE packet data."""
    __slots__ = ('packet_id', 'topics')

    def __init__(self):
        self.packet_id = None
        self.topics = []  # List of (topic_filter_bytes, qos) tuples


class UnsubscribeData:
    """Parsed UNSUBSCRIBE packet data."""
    __slots__ = ('packet_id', 'topics')

    def __init__(self):
        self.packet_id = None
        self.topics = []  # List of topic_filter_bytes


async def read_packet(reader):
    """
    Read one complete MQTT packet from asyncio StreamReader.

    Returns:
        tuple: (packet_type, flags, payload_bytes)

    Raises:
        MQTTProtocolError: If packet format is invalid
        OSError: If connection is closed or network error
    """
    # Read fixed header first byte
    first_byte_data = await reader.readexactly(1)
    first_byte = first_byte_data[0]

    packet_type = (first_byte >> 4) & 0x0F
    flags = first_byte & 0x0F

    # Read remaining length (variable length 1-4 bytes with continuation bit)
    remaining_length = 0
    multiplier = 1
    byte_count = 0

    while True:
        if byte_count >= 4:
            raise MQTTProtocolError('Remaining length exceeds 4 bytes')

        byte_data = await reader.readexactly(1)
        byte = byte_data[0]
        byte_count += 1

        remaining_length += (byte & 0x7F) * multiplier

        if (byte & 0x80) == 0:
            break

        multiplier *= 128

        if multiplier > 128 * 128 * 128:
            raise MQTTProtocolError('Remaining length multiplier overflow')

    # Validate remaining length
    if remaining_length > 268435455:  # Maximum allowed by MQTT spec
        raise MQTTProtocolError('Remaining length too large')

    # Read payload
    if remaining_length > 0:
        payload = await reader.readexactly(remaining_length)
    else:
        payload = b''

    return (packet_type, flags, payload)


def parse_connect(data):
    """
    Parse CONNECT packet payload.

    Args:
        data: Payload bytes from CONNECT packet

    Returns:
        ConnectData: Parsed connection data

    Raises:
        MQTTProtocolError: If packet format is invalid
    """
    if len(data) < 10:
        raise MQTTProtocolError('CONNECT packet too short')

    connect = ConnectData()
    offset = 0

    # Protocol name (2-byte length + string)
    protocol_name_len = struct.unpack_from('!H', data, offset)[0]
    offset += 2

    if offset + protocol_name_len > len(data):
        raise MQTTProtocolError('Protocol name length exceeds packet')

    connect.protocol_name = bytes(data[offset:offset + protocol_name_len])
    offset += protocol_name_len

    if connect.protocol_name != b'MQTT':
        raise MQTTProtocolError('Invalid protocol name: %s' % connect.protocol_name)

    # Protocol level
    if offset >= len(data):
        raise MQTTProtocolError('Missing protocol level')

    connect.protocol_level = data[offset]
    offset += 1

    if connect.protocol_level != 4:
        raise MQTTProtocolError('Unsupported protocol level: %d' % connect.protocol_level)

    # Connect flags
    if offset >= len(data):
        raise MQTTProtocolError('Missing connect flags')

    flags = data[offset]
    offset += 1

    # Check reserved bit (bit 0 must be 0)
    if flags & 0x01:
        raise MQTTProtocolError('Reserved bit in connect flags is not 0')

    connect.has_username = bool(flags & 0x80)
    connect.has_password = bool(flags & 0x40)
    connect.will_retain = bool(flags & 0x20)
    connect.will_qos = (flags >> 3) & 0x03
    connect.has_will = bool(flags & 0x04)
    connect.clean_session = bool(flags & 0x02)

    # Validate will flags
    if not connect.has_will:
        if connect.will_qos != 0 or connect.will_retain:
            raise MQTTProtocolError('Will QoS/Retain set but Will flag is 0')

    if connect.will_qos > 2:
        raise MQTTProtocolError('Invalid Will QoS: %d' % connect.will_qos)

    # Keep alive (2 bytes)
    if offset + 2 > len(data):
        raise MQTTProtocolError('Missing keep alive')

    connect.keep_alive = struct.unpack_from('!H', data, offset)[0]
    offset += 2

    # Client ID (required)
    client_id, offset = decode_utf8_string(data, offset)
    connect.client_id = client_id

    # Will topic and message (if will flag set)
    if connect.has_will:
        will_topic, offset = decode_utf8_string(data, offset)
        connect.will_topic = will_topic

        will_message, offset = decode_utf8_string(data, offset)
        connect.will_message = will_message

    # Username (if username flag set)
    if connect.has_username:
        username, offset = decode_utf8_string(data, offset)
        connect.username = username

    # Password (if password flag set)
    if connect.has_password:
        password, offset = decode_utf8_string(data, offset)
        connect.password = password

    # Validate all data consumed
    if offset != len(data):
        raise MQTTProtocolError('Extra data in CONNECT packet')

    return connect


def parse_publish(data, flags):
    """
    Parse PUBLISH packet payload.

    Args:
        data: Payload bytes from PUBLISH packet
        flags: Flags from fixed header

    Returns:
        PublishData: Parsed publish data

    Raises:
        MQTTProtocolError: If packet format is invalid
    """
    if len(data) < 2:
        raise MQTTProtocolError('PUBLISH packet too short')

    publish = PublishData()
    offset = 0

    # Extract flags
    publish.dup = bool((flags >> 3) & 0x01)
    publish.qos = (flags >> 1) & 0x03
    publish.retain = bool(flags & 0x01)

    # Validate QoS
    if publish.qos > 2:
        raise MQTTProtocolError('Invalid PUBLISH QoS: %d' % publish.qos)

    # Topic name
    topic, offset = decode_utf8_string(data, offset)
    publish.topic = topic

    # Validate topic (must not be empty, must not contain wildcards)
    if len(publish.topic) == 0:
        raise MQTTProtocolError('Empty topic in PUBLISH')

    if b'+' in publish.topic or b'#' in publish.topic:
        raise MQTTProtocolError('Wildcards not allowed in PUBLISH topic')

    # Packet ID (only for QoS > 0)
    if publish.qos > 0:
        if offset + 2 > len(data):
            raise MQTTProtocolError('Missing packet ID in PUBLISH')

        publish.packet_id = struct.unpack_from('!H', data, offset)[0]
        offset += 2

        if publish.packet_id == 0:
            raise MQTTProtocolError('Packet ID cannot be 0')

    # Payload (rest of packet - can be empty)
    # Use memoryview to avoid copying on MicroPython; materialize to bytes for storage
    try:
        publish.payload = bytes(memoryview(data)[offset:])
    except TypeError:
        publish.payload = bytes(data[offset:])

    return publish


def parse_subscribe(data):
    """
    Parse SUBSCRIBE packet payload.

    Args:
        data: Payload bytes from SUBSCRIBE packet

    Returns:
        SubscribeData: Parsed subscribe data

    Raises:
        MQTTProtocolError: If packet format is invalid
    """
    if len(data) < 5:  # Minimum: 2 bytes packet ID + 2 bytes topic length + 1 byte QoS
        raise MQTTProtocolError('SUBSCRIBE packet too short')

    subscribe = SubscribeData()
    offset = 0

    # Packet ID
    subscribe.packet_id = struct.unpack_from('!H', data, offset)[0]
    offset += 2

    if subscribe.packet_id == 0:
        raise MQTTProtocolError('Packet ID cannot be 0')

    # Topic filters (at least one required)
    while offset < len(data):
        # Topic filter
        topic_filter, new_offset = decode_utf8_string(data, offset)
        offset = new_offset

        if len(topic_filter) == 0:
            raise MQTTProtocolError('Empty topic filter in SUBSCRIBE')

        # QoS byte
        if offset >= len(data):
            raise MQTTProtocolError('Missing QoS for topic filter')

        qos = data[offset]
        offset += 1

        if qos > 2:
            raise MQTTProtocolError('Invalid QoS in SUBSCRIBE: %d' % qos)

        subscribe.topics.append((topic_filter, qos))

    # Must have at least one topic
    if len(subscribe.topics) == 0:
        raise MQTTProtocolError('SUBSCRIBE must contain at least one topic')

    return subscribe


def parse_unsubscribe(data):
    """
    Parse UNSUBSCRIBE packet payload.

    Args:
        data: Payload bytes from UNSUBSCRIBE packet

    Returns:
        UnsubscribeData: Parsed unsubscribe data

    Raises:
        MQTTProtocolError: If packet format is invalid
    """
    if len(data) < 4:  # Minimum: 2 bytes packet ID + 2 bytes topic length
        raise MQTTProtocolError('UNSUBSCRIBE packet too short')

    unsubscribe = UnsubscribeData()
    offset = 0

    # Packet ID
    unsubscribe.packet_id = struct.unpack_from('!H', data, offset)[0]
    offset += 2

    if unsubscribe.packet_id == 0:
        raise MQTTProtocolError('Packet ID cannot be 0')

    # Topic filters (at least one required)
    while offset < len(data):
        topic_filter, new_offset = decode_utf8_string(data, offset)
        offset = new_offset

        if len(topic_filter) == 0:
            raise MQTTProtocolError('Empty topic filter in UNSUBSCRIBE')

        unsubscribe.topics.append(topic_filter)

    # Must have at least one topic
    if len(unsubscribe.topics) == 0:
        raise MQTTProtocolError('UNSUBSCRIBE must contain at least one topic')

    return unsubscribe


def build_connack(session_present, return_code):
    """
    Build CONNACK packet.

    Args:
        session_present: Boolean indicating if session is present
        return_code: Connection return code (0 = accepted)

    Returns:
        bytes: Complete CONNACK packet
    """
    session_byte = 0x01 if session_present else 0x00
    return bytes([0x20, 0x02, session_byte, return_code])


def build_publish(topic, payload, qos=0, retain=False, dup=False, packet_id=None):
    """
    Build PUBLISH packet.

    Args:
        topic: Topic name (bytes)
        payload: Message payload (bytes)
        qos: Quality of Service (0, 1, or 2)
        retain: Retain flag
        dup: Duplicate flag
        packet_id: Packet ID (required if qos > 0)

    Returns:
        bytes: Complete PUBLISH packet

    Raises:
        MQTTProtocolError: If parameters are invalid
    """
    if qos > 2:
        raise MQTTProtocolError('Invalid QoS: %d' % qos)

    if qos > 0 and packet_id is None:
        raise MQTTProtocolError('Packet ID required for QoS > 0')

    if qos > 0 and packet_id == 0:
        raise MQTTProtocolError('Packet ID cannot be 0')

    # Build fixed header first byte
    first_byte = (PUBLISH << 4) | (int(dup) << 3) | (qos << 1) | int(retain)

    # Build variable header
    topic_encoded = encode_utf8_string(topic)

    if qos > 0:
        packet_id_bytes = struct.pack('!H', packet_id)
        variable_header = topic_encoded + packet_id_bytes
    else:
        variable_header = topic_encoded

    # Calculate remaining length
    remaining_length = len(variable_header) + len(payload)
    remaining_length_bytes = encode_remaining_length(remaining_length)

    # Assemble packet
    packet = bytearray(1 + len(remaining_length_bytes) + remaining_length)
    offset = 0

    packet[offset] = first_byte
    offset += 1

    packet[offset:offset + len(remaining_length_bytes)] = remaining_length_bytes
    offset += len(remaining_length_bytes)

    packet[offset:offset + len(variable_header)] = variable_header
    offset += len(variable_header)

    packet[offset:offset + len(payload)] = payload

    return bytes(packet)


def build_puback(packet_id):
    """
    Build PUBACK packet.

    Args:
        packet_id: Packet ID to acknowledge

    Returns:
        bytes: Complete PUBACK packet (4 bytes)
    """
    return bytes([0x40, 0x02]) + struct.pack('!H', packet_id)


def build_pubrec(packet_id):
    """
    Build PUBREC packet.

    Args:
        packet_id: Packet ID to acknowledge

    Returns:
        bytes: Complete PUBREC packet (4 bytes)
    """
    return bytes([0x50, 0x02]) + struct.pack('!H', packet_id)


def build_pubrel(packet_id):
    """
    Build PUBREL packet.

    Args:
        packet_id: Packet ID to release

    Returns:
        bytes: Complete PUBREL packet (4 bytes)
    """
    # Note: PUBREL has flags = 0x02 (bit 1 set) per MQTT 3.1.1 spec
    return bytes([0x62, 0x02]) + struct.pack('!H', packet_id)


def build_pubcomp(packet_id):
    """
    Build PUBCOMP packet.

    Args:
        packet_id: Packet ID to complete

    Returns:
        bytes: Complete PUBCOMP packet (4 bytes)
    """
    return bytes([0x70, 0x02]) + struct.pack('!H', packet_id)


def build_suback(packet_id, granted_qos_list):
    """
    Build SUBACK packet.

    Args:
        packet_id: Packet ID from SUBSCRIBE
        granted_qos_list: List of granted QoS values (0, 1, 2, or 0x80 for failure)

    Returns:
        bytes: Complete SUBACK packet
    """
    payload_len = len(granted_qos_list)
    remaining_length = 2 + payload_len
    remaining_length_bytes = encode_remaining_length(remaining_length)

    pkt = bytearray(1 + len(remaining_length_bytes) + remaining_length)
    offset = 0

    # Fixed header
    pkt[offset] = 0x90
    offset += 1
    pkt[offset:offset + len(remaining_length_bytes)] = remaining_length_bytes
    offset += len(remaining_length_bytes)

    # Variable header: packet ID
    struct.pack_into('!H', pkt, offset, packet_id)
    offset += 2

    # Payload: granted QoS values
    for i, qos in enumerate(granted_qos_list):
        pkt[offset + i] = qos

    return bytes(pkt)


def build_unsuback(packet_id):
    """
    Build UNSUBACK packet.

    Args:
        packet_id: Packet ID from UNSUBSCRIBE

    Returns:
        bytes: Complete UNSUBACK packet (4 bytes)
    """
    return bytes([0xB0, 0x02]) + struct.pack('!H', packet_id)
