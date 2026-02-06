"""
pytest configuration and fixtures for BeehiveMQTT tests.

IMPORTANT: micropython_compat must be imported first to patch time/gc functions.
"""

# Apply MicroPython compatibility patches FIRST
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
import micropython_compat  # noqa: F401

import struct
import pytest
import asyncio
from beehivemqtt.config import BrokerConfig
from beehivemqtt.topic import TopicTree
from beehivemqtt.session import ClientSession
from beehivemqtt.broker import MQTTBroker
from beehivemqtt.utils import encode_utf8_string


# Configure pytest-asyncio to use "auto" mode for all async tests
pytest_plugins = ('pytest_asyncio',)


class MockWriter:
    """Mock StreamWriter for testing."""

    def __init__(self):
        self.data = bytearray()
        self._closed = False
        self._drain_error = None

    def write(self, data):
        """Write data to buffer."""
        if self._closed:
            raise OSError("Writer is closed")
        self.data.extend(data)

    async def drain(self):
        """Mock drain - raises _drain_error if set (simulates backpressure)."""
        if self._drain_error:
            raise self._drain_error
        pass

    def close(self):
        """Mark writer as closed."""
        self._closed = True

    async def wait_closed(self):
        """Mock wait_closed - no-op."""
        pass

    def get_data(self):
        """Get all written data."""
        return bytes(self.data)

    def clear(self):
        """Clear written data."""
        self.data.clear()


class MockReader:
    """Mock StreamReader for testing."""

    def __init__(self, data=b''):
        """Initialize with optional data to read."""
        self._data = data
        self._pos = 0

    async def read(self, n):
        """Read up to n bytes."""
        chunk = self._data[self._pos:self._pos + n]
        self._pos += len(chunk)
        return bytes(chunk)

    async def readexactly(self, n):
        """Read exactly n bytes (or raise if not enough)."""
        chunk = self._data[self._pos:self._pos + n]
        if len(chunk) < n:
            raise asyncio.IncompleteReadError(chunk, n)
        self._pos += n
        return bytes(chunk)

    async def readline(self):
        """Read until newline."""
        start = self._pos
        idx = self._data.find(b'\n', start)
        if idx == -1:
            chunk = self._data[start:]
            self._pos = len(self._data)
        else:
            chunk = self._data[start:idx + 1]
            self._pos = idx + 1
        return bytes(chunk)

    def set_data(self, data):
        """Replace reader data and reset position."""
        self._data = data
        self._pos = 0

    def feed(self, data):
        """Append data to end of buffer."""
        self._data = self._data + data


class SequentialMockReader:
    """MockReader that feeds packets one at a time from a list.

    Each call to readexactly reads from the current packet buffer.
    When a packet is exhausted, moves to the next one.
    Raises IncompleteReadError when all packets are consumed.
    """

    def __init__(self, packets=None):
        self._packets = list(packets or [])
        self._buf = b''
        self._pos = 0

    def add_packet(self, data):
        """Add a packet to the queue."""
        self._packets.append(data)

    async def readexactly(self, n):
        """Read exactly n bytes, moving through packets as needed."""
        result = bytearray()
        while len(result) < n:
            if self._pos >= len(self._buf):
                if not self._packets:
                    raise asyncio.IncompleteReadError(bytes(result), n)
                self._buf = self._packets.pop(0)
                self._pos = 0
            available = self._buf[self._pos:self._pos + (n - len(result))]
            result.extend(available)
            self._pos += len(available)
        return bytes(result)

    async def read(self, n):
        """Read up to n bytes."""
        try:
            return await self.readexactly(n)
        except asyncio.IncompleteReadError as e:
            return e.partial


class MQTTPacketHelper:
    """Helper class to build raw MQTT packet bytes for testing."""

    @staticmethod
    def build_connect_bytes(client_id='test', clean_session=True, keep_alive=60,
                            username=None, password=None,
                            will_topic=None, will_message=None,
                            will_qos=0, will_retain=False,
                            protocol_name=b'MQTT', protocol_level=4):
        """Build complete CONNECT packet bytes (fixed header + payload)."""
        payload = bytearray()
        payload.extend(encode_utf8_string(protocol_name))
        payload.append(protocol_level)

        flags = 0
        if clean_session:
            flags |= 0x02
        if username:
            flags |= 0x80
        if password:
            flags |= 0x40
        if will_topic is not None:
            flags |= 0x04
            flags |= (will_qos << 3)
            if will_retain:
                flags |= 0x20

        payload.append(flags)
        payload.extend(struct.pack('!H', keep_alive))
        payload.extend(encode_utf8_string(client_id))

        if will_topic is not None:
            payload.extend(encode_utf8_string(will_topic))
            payload.extend(encode_utf8_string(will_message or ''))

        if username:
            payload.extend(encode_utf8_string(username))
        if password:
            payload.extend(encode_utf8_string(password))

        # Build fixed header
        header = bytearray()
        header.append(0x10)  # CONNECT = 1 << 4

        # Encode remaining length
        length = len(payload)
        while True:
            byte = length % 128
            length = length // 128
            if length > 0:
                byte |= 0x80
            header.append(byte)
            if length == 0:
                break

        return bytes(header + payload)

    @staticmethod
    def build_publish_bytes(topic, payload=b'', qos=0, retain=False,
                            dup=False, packet_id=None):
        """Build complete PUBLISH packet bytes."""
        from beehivemqtt.packet import build_publish
        return build_publish(
            topic if isinstance(topic, bytes) else topic.encode('utf-8'),
            payload if isinstance(payload, bytes) else payload.encode('utf-8'),
            qos=qos, retain=retain, dup=dup, packet_id=packet_id
        )

    @staticmethod
    def build_subscribe_bytes(packet_id, topics):
        """Build complete SUBSCRIBE packet bytes.

        Args:
            packet_id: int
            topics: list of (topic_filter_str, qos) tuples
        """
        from beehivemqtt.packet import build_suback
        from beehivemqtt.utils import encode_remaining_length

        var_header = struct.pack('!H', packet_id)
        sub_payload = bytearray()
        for tf, qos in topics:
            sub_payload.extend(encode_utf8_string(tf))
            sub_payload.append(qos)

        remaining = len(var_header) + len(sub_payload)
        header = bytearray([0x82])  # SUBSCRIBE with required flags
        header.extend(encode_remaining_length(remaining))
        return bytes(header + var_header + sub_payload)

    @staticmethod
    def build_unsubscribe_bytes(packet_id, topics):
        """Build complete UNSUBSCRIBE packet bytes.

        Args:
            packet_id: int
            topics: list of topic_filter strings
        """
        from beehivemqtt.utils import encode_remaining_length

        var_header = struct.pack('!H', packet_id)
        unsub_payload = bytearray()
        for tf in topics:
            unsub_payload.extend(encode_utf8_string(tf))

        remaining = len(var_header) + len(unsub_payload)
        header = bytearray([0xA2])  # UNSUBSCRIBE with required flags
        header.extend(encode_remaining_length(remaining))
        return bytes(header + var_header + unsub_payload)

    @staticmethod
    def build_disconnect_bytes():
        """Build DISCONNECT packet bytes."""
        return bytes([0xE0, 0x00])

    @staticmethod
    def build_pingreq_bytes():
        """Build PINGREQ packet bytes."""
        return bytes([0xC0, 0x00])


# Fixtures

@pytest.fixture
def broker_config():
    """Provide a BrokerConfig with test defaults."""
    return BrokerConfig(
        port=1883,
        max_clients=5,
        max_subscriptions_per_client=10,
        max_payload_size=1024,
        max_retained_messages=20,
        connect_timeout=5,
        log_level='ERROR'  # Quiet during tests
    )


@pytest.fixture
def topic_tree():
    """Provide a fresh TopicTree instance."""
    return TopicTree()


@pytest.fixture
def mock_writer():
    """Provide a MockWriter instance."""
    return MockWriter()


@pytest.fixture
def mock_reader():
    """Provide a MockReader instance."""
    return MockReader()


@pytest.fixture
def client_session(mock_reader, mock_writer):
    """Provide a ClientSession with mock reader/writer."""
    session = ClientSession('test-client', clean_session=True)
    session.reader = mock_reader
    session.writer = mock_writer
    session.connected = True
    session.update_activity()
    return session


@pytest.fixture
def configured_broker():
    """Provide a configured MQTTBroker ready for integration testing."""
    config = BrokerConfig(
        port=1883,
        max_clients=10,
        max_subscriptions_per_client=20,
        max_payload_size=4096,
        max_retained_messages=50,
        connect_timeout=5,
        log_level='ERROR',
        sys_topics_enabled=False
    )
    broker = MQTTBroker(config=config)
    return broker


@pytest.fixture
def pkt():
    """Provide MQTTPacketHelper instance."""
    return MQTTPacketHelper()
