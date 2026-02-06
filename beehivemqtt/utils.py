"""
BeehiveMQTT utility functions.

Implements MQTT 3.1.1 protocol encoding/decoding and validation utilities.
"""

import struct
import time


def encode_remaining_length(length):
    """Encode remaining length per MQTT §2.2.3 variable-length encoding.

    Args:
        length: Integer 0-268435455

    Returns:
        bytearray of 1-4 bytes
    """
    if length < 0 or length > 268435455:
        raise ValueError("Remaining length must be 0-268435455")

    result = bytearray()
    while True:
        byte = length % 128
        length = length // 128
        if length > 0:
            byte |= 0x80
        result.append(byte)
        if length == 0:
            break
    return result


def decode_remaining_length(data, offset=0):
    """Decode MQTT remaining length from bytes.

    Args:
        data: bytes/bytearray containing encoded length
        offset: starting position in data

    Returns:
        (value, bytes_consumed) tuple
    """
    multiplier = 1
    value = 0
    byte_count = 0

    while True:
        if byte_count >= 4:
            raise ValueError("Malformed remaining length")
        byte = data[offset + byte_count]
        byte_count += 1
        value += (byte & 0x7F) * multiplier
        if (byte & 0x80) == 0:
            break
        multiplier *= 128

    return (value, byte_count)


def encode_utf8_string(s):
    """Encode MQTT UTF-8 string with length prefix.

    Args:
        s: str or bytes

    Returns:
        bytearray with 2-byte big-endian length + encoded string
    """
    if isinstance(s, str):
        s = s.encode('utf-8')
    result = bytearray(struct.pack('!H', len(s)))
    result.extend(s)
    return result


def decode_utf8_string(data, offset=0):
    """Decode MQTT UTF-8 string from bytes.

    Args:
        data: bytes/bytearray
        offset: starting position

    Returns:
        (decoded_bytes, new_offset) tuple
    """
    length = struct.unpack_from('!H', data, offset)[0]
    string_data = bytes(data[offset + 2:offset + 2 + length])
    return (string_data, offset + 2 + length)


def validate_topic_name(topic, max_length=256):
    """Validate MQTT topic name (for PUBLISH).

    Args:
        topic: bytes or str
        max_length: maximum allowed length

    Returns:
        True if valid

    Raises:
        ValueError if invalid
    """
    if isinstance(topic, str):
        topic = topic.encode('utf-8')

    if not topic:
        raise ValueError("Topic name cannot be empty")
    if len(topic) > max_length:
        raise ValueError("Topic name exceeds maximum length")
    if b'+' in topic or b'#' in topic:
        raise ValueError("Topic name cannot contain wildcards")

    return True


def validate_topic_filter(topic_filter, max_length=256):
    """Validate MQTT topic filter (for SUBSCRIBE).

    Args:
        topic_filter: bytes or str
        max_length: maximum allowed length

    Returns:
        True if valid

    Raises:
        ValueError if invalid
    """
    if isinstance(topic_filter, str):
        topic_filter = topic_filter.encode('utf-8')

    if not topic_filter:
        raise ValueError("Topic filter cannot be empty")
    if len(topic_filter) > max_length:
        raise ValueError("Topic filter exceeds maximum length")

    # Check '#' - only allowed as last char after '/' or alone
    hash_pos = topic_filter.find(b'#')
    if hash_pos != -1:
        if hash_pos != len(topic_filter) - 1:
            raise ValueError("# wildcard must be last character")
        if hash_pos > 0 and topic_filter[hash_pos - 1:hash_pos] != b'/':
            raise ValueError("# must be alone or after /")

    # Check '+' - must occupy entire level
    levels = topic_filter.split(b'/')
    for level in levels:
        if b'+' in level and level != b'+':
            raise ValueError("+ must occupy entire level")

    return True


_client_id_counter = 0

def generate_client_id():
    """Generate a unique client ID for MQTT broker.

    Uses a module-level counter XORed with time seed to avoid collisions.

    Returns:
        str in format "beehive-XXXXXXXX"
    """
    global _client_id_counter
    _client_id_counter += 1

    try:
        # MicroPython
        seed = time.ticks_ms() ^ (time.ticks_cpu() & 0xFFFFFFFF)
    except AttributeError:
        # CPython fallback
        seed = int(time.time() * 1000)

    return "beehive-%08x" % ((seed ^ _client_id_counter) & 0xFFFFFFFF)
