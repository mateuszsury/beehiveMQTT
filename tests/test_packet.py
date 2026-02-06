"""Tests for beehivemqtt.packet module."""

import pytest
import struct
from beehivemqtt import packet
from beehivemqtt.packet import (
    ConnectData, PublishData, SubscribeData, UnsubscribeData,
    parse_connect, parse_publish, parse_subscribe, parse_unsubscribe,
    build_connack, build_publish, build_puback, build_pubrec,
    build_pubrel, build_pubcomp, build_suback, build_unsuback,
    PINGRESP_BYTES, CONNACK_ACCEPTED
)
from beehivemqtt.utils import encode_utf8_string
from beehivemqtt.errors import MQTTProtocolError


class TestConnackPacket:
    """Test CONNACK packet building."""

    def test_build_connack_accepted(self):
        """Test building CONNACK with accepted status."""
        pkt = build_connack(session_present=False, return_code=CONNACK_ACCEPTED)
        assert pkt == bytes([0x20, 0x02, 0x00, 0x00])

    def test_build_connack_session_present(self):
        """Test building CONNACK with session present flag."""
        pkt = build_connack(session_present=True, return_code=CONNACK_ACCEPTED)
        assert pkt == bytes([0x20, 0x02, 0x01, 0x00])

    def test_build_connack_refused(self):
        """Test building CONNACK with refused status."""
        pkt = build_connack(session_present=False, return_code=0x04)
        assert pkt == bytes([0x20, 0x02, 0x00, 0x04])


class TestConnectPacket:
    """Test CONNECT packet parsing."""

    def build_connect_packet(self, client_id='test', clean_session=True, keep_alive=60,
                            username=None, password=None, will=None):
        """Helper to build CONNECT packet payload."""
        data = bytearray()

        # Protocol name
        data.extend(encode_utf8_string(b'MQTT'))

        # Protocol level
        data.append(4)

        # Connect flags
        flags = 0
        if clean_session:
            flags |= 0x02
        if username:
            flags |= 0x80
        if password:
            flags |= 0x40
        if will:
            flags |= 0x04
            flags |= (will.get('qos', 0) << 3)
            if will.get('retain', False):
                flags |= 0x20

        data.append(flags)

        # Keep alive
        data.extend(struct.pack('!H', keep_alive))

        # Client ID
        data.extend(encode_utf8_string(client_id))

        # Will
        if will:
            data.extend(encode_utf8_string(will['topic']))
            data.extend(encode_utf8_string(will['message']))

        # Username
        if username:
            data.extend(encode_utf8_string(username))

        # Password
        if password:
            data.extend(encode_utf8_string(password))

        return bytes(data)

    def test_parse_connect_minimal(self):
        """Test parsing minimal CONNECT packet."""
        data = self.build_connect_packet(client_id='client1')
        connect = parse_connect(data)

        assert connect.protocol_name == b'MQTT'
        assert connect.protocol_level == 4
        assert connect.clean_session is True
        assert connect.keep_alive == 60
        assert connect.client_id == b'client1'
        assert connect.has_will is False
        assert connect.has_username is False
        assert connect.has_password is False

    def test_parse_connect_with_username_password(self):
        """Test parsing CONNECT with username and password."""
        data = self.build_connect_packet(
            client_id='client2',
            username='user1',
            password='pass1'
        )
        connect = parse_connect(data)

        assert connect.client_id == b'client2'
        assert connect.has_username is True
        assert connect.has_password is True
        assert connect.username == b'user1'
        assert connect.password == b'pass1'

    def test_parse_connect_with_will(self):
        """Test parsing CONNECT with will message."""
        data = self.build_connect_packet(
            client_id='client3',
            will={'topic': 'will/topic', 'message': 'offline', 'qos': 1, 'retain': True}
        )
        connect = parse_connect(data)

        assert connect.has_will is True
        assert connect.will_topic == b'will/topic'
        assert connect.will_message == b'offline'
        assert connect.will_qos == 1
        assert connect.will_retain is True

    def test_parse_connect_zero_keep_alive(self):
        """Test parsing CONNECT with keep-alive disabled."""
        data = self.build_connect_packet(keep_alive=0)
        connect = parse_connect(data)
        assert connect.keep_alive == 0

    def test_parse_connect_empty_client_id(self):
        """Test parsing CONNECT with empty client ID."""
        data = self.build_connect_packet(client_id='')
        connect = parse_connect(data)
        assert connect.client_id == b''

    def test_parse_connect_invalid_protocol(self):
        """Test parsing CONNECT with invalid protocol name."""
        data = bytearray()
        data.extend(encode_utf8_string(b'XXXX'))
        data.append(4)
        data.append(0x02)
        data.extend(struct.pack('!H', 60))
        data.extend(encode_utf8_string('test'))

        with pytest.raises(MQTTProtocolError, match="Invalid protocol name"):
            parse_connect(bytes(data))

    def test_parse_connect_invalid_level(self):
        """Test parsing CONNECT with unsupported protocol level."""
        data = bytearray()
        data.extend(encode_utf8_string(b'MQTT'))
        data.append(3)  # Wrong level
        data.append(0x02)
        data.extend(struct.pack('!H', 60))
        data.extend(encode_utf8_string('test'))

        with pytest.raises(MQTTProtocolError, match="Unsupported protocol level"):
            parse_connect(bytes(data))

    def test_parse_connect_reserved_bit_set(self):
        """Test parsing CONNECT with reserved bit set raises error."""
        data = bytearray()
        data.extend(encode_utf8_string(b'MQTT'))
        data.append(4)
        data.append(0x03)  # Reserved bit set
        data.extend(struct.pack('!H', 60))
        data.extend(encode_utf8_string('test'))

        with pytest.raises(MQTTProtocolError, match="Reserved bit"):
            parse_connect(bytes(data))


class TestPublishPacket:
    """Test PUBLISH packet building and parsing."""

    def test_build_publish_qos0(self):
        """Test building PUBLISH packet with QoS 0."""
        pkt = build_publish(b'test/topic', b'hello', qos=0, retain=False)

        # Fixed header: 0x30 (PUBLISH, QoS 0, no DUP, no RETAIN)
        assert pkt[0] == 0x30
        # Should contain topic and payload
        assert b'test/topic' in pkt
        assert b'hello' in pkt

    def test_build_publish_qos1(self):
        """Test building PUBLISH packet with QoS 1."""
        pkt = build_publish(b'topic', b'payload', qos=1, retain=False, packet_id=42)

        # Fixed header: 0x32 (PUBLISH, QoS 1)
        assert pkt[0] == 0x32
        assert b'topic' in pkt
        assert b'payload' in pkt

    def test_build_publish_qos2_with_retain(self):
        """Test building PUBLISH packet with QoS 2 and retain."""
        pkt = build_publish(b'topic', b'data', qos=2, retain=True, packet_id=100)

        # Fixed header: 0x35 (PUBLISH, QoS 2, RETAIN)
        assert pkt[0] == 0x35

    def test_build_publish_with_dup(self):
        """Test building PUBLISH packet with DUP flag."""
        pkt = build_publish(b'topic', b'data', qos=1, retain=False, dup=True, packet_id=50)

        # Fixed header: 0x3A (PUBLISH, QoS 1, DUP)
        assert pkt[0] == 0x3A

    def test_build_publish_qos_requires_packet_id(self):
        """Test building PUBLISH with QoS > 0 requires packet_id."""
        with pytest.raises(MQTTProtocolError, match="Packet ID required"):
            build_publish(b'topic', b'data', qos=1)

    def test_build_publish_packet_id_cannot_be_zero(self):
        """Test building PUBLISH with packet_id=0 raises error."""
        with pytest.raises(MQTTProtocolError, match="Packet ID cannot be 0"):
            build_publish(b'topic', b'data', qos=1, packet_id=0)

    def test_parse_publish_qos0(self):
        """Test parsing PUBLISH packet with QoS 0."""
        # Build manually: PUBLISH QoS 0, no retain
        data = encode_utf8_string(b'test/topic') + b'hello world'
        flags = 0x00  # QoS 0, no DUP, no RETAIN

        publish = parse_publish(data, flags)

        assert publish.topic == b'test/topic'
        assert publish.payload == b'hello world'
        assert publish.qos == 0
        assert publish.retain is False
        assert publish.dup is False
        assert publish.packet_id is None

    def test_parse_publish_qos1(self):
        """Test parsing PUBLISH packet with QoS 1."""
        data = encode_utf8_string(b'topic') + struct.pack('!H', 42) + b'payload'
        flags = 0x02  # QoS 1

        publish = parse_publish(data, flags)

        assert publish.topic == b'topic'
        assert publish.payload == b'payload'
        assert publish.qos == 1
        assert publish.packet_id == 42

    def test_parse_publish_qos2_with_retain(self):
        """Test parsing PUBLISH packet with QoS 2 and retain."""
        data = encode_utf8_string(b'topic') + struct.pack('!H', 100) + b'data'
        flags = 0x05  # QoS 2, RETAIN

        publish = parse_publish(data, flags)

        assert publish.qos == 2
        assert publish.retain is True
        assert publish.packet_id == 100

    def test_parse_publish_with_dup(self):
        """Test parsing PUBLISH packet with DUP flag."""
        data = encode_utf8_string(b'topic') + struct.pack('!H', 50) + b'data'
        flags = 0x0A  # QoS 1, DUP

        publish = parse_publish(data, flags)

        assert publish.dup is True
        assert publish.qos == 1

    def test_parse_publish_empty_payload(self):
        """Test parsing PUBLISH with empty payload."""
        data = encode_utf8_string(b'topic')
        flags = 0x00

        publish = parse_publish(data, flags)

        assert publish.topic == b'topic'
        assert publish.payload == b''

    def test_parse_publish_empty_topic_raises_error(self):
        """Test parsing PUBLISH with empty topic raises error."""
        data = encode_utf8_string(b'') + b'payload'
        flags = 0x00

        with pytest.raises(MQTTProtocolError, match="Empty topic"):
            parse_publish(data, flags)

    def test_parse_publish_wildcard_in_topic_raises_error(self):
        """Test parsing PUBLISH with wildcard in topic raises error."""
        data = encode_utf8_string(b'test/+/topic') + b'payload'
        flags = 0x00

        with pytest.raises(MQTTProtocolError, match="Wildcards not allowed"):
            parse_publish(data, flags)

    def test_roundtrip_publish_qos0(self):
        """Test build then parse roundtrip for QoS 0 PUBLISH."""
        topic = b'test/topic'
        payload = b'test payload'

        pkt = build_publish(topic, payload, qos=0, retain=True)

        # Extract data and flags from built packet
        flags = pkt[0] & 0x0F
        # Skip fixed header to get variable header + payload
        remaining_len = pkt[1]
        data = pkt[2:2 + remaining_len]

        publish = parse_publish(data, flags)

        assert publish.topic == topic
        assert publish.payload == payload
        assert publish.qos == 0
        assert publish.retain is True


class TestSubscribePacket:
    """Test SUBSCRIBE packet parsing."""

    def test_parse_subscribe_single_topic(self):
        """Test parsing SUBSCRIBE with single topic."""
        data = bytearray()
        data.extend(struct.pack('!H', 1))  # Packet ID
        data.extend(encode_utf8_string(b'test/topic'))
        data.append(0)  # QoS 0

        subscribe = parse_subscribe(bytes(data))

        assert subscribe.packet_id == 1
        assert len(subscribe.topics) == 1
        assert subscribe.topics[0] == (b'test/topic', 0)

    def test_parse_subscribe_multiple_topics(self):
        """Test parsing SUBSCRIBE with multiple topics."""
        data = bytearray()
        data.extend(struct.pack('!H', 42))
        data.extend(encode_utf8_string(b'topic1'))
        data.append(0)
        data.extend(encode_utf8_string(b'topic2'))
        data.append(1)
        data.extend(encode_utf8_string(b'topic3'))
        data.append(2)

        subscribe = parse_subscribe(bytes(data))

        assert subscribe.packet_id == 42
        assert len(subscribe.topics) == 3
        assert subscribe.topics[0] == (b'topic1', 0)
        assert subscribe.topics[1] == (b'topic2', 1)
        assert subscribe.topics[2] == (b'topic3', 2)

    def test_parse_subscribe_with_wildcards(self):
        """Test parsing SUBSCRIBE with wildcard topic filters."""
        data = bytearray()
        data.extend(struct.pack('!H', 10))
        data.extend(encode_utf8_string(b'home/+/temperature'))
        data.append(1)
        data.extend(encode_utf8_string(b'sensor/#'))
        data.append(2)

        subscribe = parse_subscribe(bytes(data))

        assert len(subscribe.topics) == 2
        assert subscribe.topics[0] == (b'home/+/temperature', 1)
        assert subscribe.topics[1] == (b'sensor/#', 2)

    def test_parse_subscribe_packet_id_zero_raises_error(self):
        """Test parsing SUBSCRIBE with packet_id=0 raises error."""
        data = bytearray()
        data.extend(struct.pack('!H', 0))
        data.extend(encode_utf8_string(b'topic'))
        data.append(0)

        with pytest.raises(MQTTProtocolError, match="Packet ID cannot be 0"):
            parse_subscribe(bytes(data))

    def test_parse_subscribe_invalid_qos_raises_error(self):
        """Test parsing SUBSCRIBE with invalid QoS raises error."""
        data = bytearray()
        data.extend(struct.pack('!H', 1))
        data.extend(encode_utf8_string(b'topic'))
        data.append(3)  # Invalid QoS

        with pytest.raises(MQTTProtocolError, match="Invalid QoS"):
            parse_subscribe(bytes(data))


class TestUnsubscribePacket:
    """Test UNSUBSCRIBE packet parsing."""

    def test_parse_unsubscribe_single_topic(self):
        """Test parsing UNSUBSCRIBE with single topic."""
        data = bytearray()
        data.extend(struct.pack('!H', 1))
        data.extend(encode_utf8_string(b'test/topic'))

        unsubscribe = parse_unsubscribe(bytes(data))

        assert unsubscribe.packet_id == 1
        assert len(unsubscribe.topics) == 1
        assert unsubscribe.topics[0] == b'test/topic'

    def test_parse_unsubscribe_multiple_topics(self):
        """Test parsing UNSUBSCRIBE with multiple topics."""
        data = bytearray()
        data.extend(struct.pack('!H', 99))
        data.extend(encode_utf8_string(b'topic1'))
        data.extend(encode_utf8_string(b'topic2'))
        data.extend(encode_utf8_string(b'topic3'))

        unsubscribe = parse_unsubscribe(bytes(data))

        assert unsubscribe.packet_id == 99
        assert len(unsubscribe.topics) == 3
        assert unsubscribe.topics == [b'topic1', b'topic2', b'topic3']


class TestQoSPackets:
    """Test QoS acknowledgment packets."""

    def test_build_puback(self):
        """Test building PUBACK packet."""
        pkt = build_puback(42)
        assert pkt == bytes([0x40, 0x02]) + struct.pack('!H', 42)

    def test_build_pubrec(self):
        """Test building PUBREC packet."""
        pkt = build_pubrec(100)
        assert pkt == bytes([0x50, 0x02]) + struct.pack('!H', 100)

    def test_build_pubrel(self):
        """Test building PUBREL packet."""
        pkt = build_pubrel(200)
        # PUBREL has flags 0x02 set per MQTT spec
        assert pkt == bytes([0x62, 0x02]) + struct.pack('!H', 200)

    def test_build_pubcomp(self):
        """Test building PUBCOMP packet."""
        pkt = build_pubcomp(300)
        assert pkt == bytes([0x70, 0x02]) + struct.pack('!H', 300)


class TestSubackPacket:
    """Test SUBACK packet building."""

    def test_build_suback_single_topic(self):
        """Test building SUBACK for single topic."""
        pkt = build_suback(1, [0])
        assert pkt[0] == 0x90  # SUBACK packet type
        assert pkt[1] == 3  # Remaining length
        assert struct.unpack_from('!H', pkt, 2)[0] == 1  # Packet ID
        assert pkt[4] == 0  # Granted QoS

    def test_build_suback_multiple_topics(self):
        """Test building SUBACK for multiple topics."""
        pkt = build_suback(42, [0, 1, 2])
        assert struct.unpack_from('!H', pkt, 2)[0] == 42
        assert pkt[4] == 0
        assert pkt[5] == 1
        assert pkt[6] == 2

    def test_build_suback_with_failure(self):
        """Test building SUBACK with subscription failure."""
        pkt = build_suback(10, [0, 0x80, 1])
        assert pkt[4] == 0
        assert pkt[5] == 0x80  # Failure
        assert pkt[6] == 1

    def test_build_suback_large_topic_list(self):
        """Test building SUBACK with >125 granted_qos entries requiring multi-byte remaining length."""
        num_topics = 130
        granted_qos = [i % 3 for i in range(num_topics)]
        packet_id = 12345

        pkt = build_suback(packet_id, granted_qos)

        # Verify first byte is SUBACK packet type
        assert pkt[0] == 0x90

        # Remaining length = 2 (packet_id) + 130 (qos entries) = 132
        # 132 > 127, so it needs 2 bytes to encode:
        #   byte 1: 132 % 128 = 4, with continuation bit: 4 | 0x80 = 0x84
        #   byte 2: 132 // 128 = 1
        assert pkt[1] == 0x84  # first byte of remaining length (4 | 0x80)
        assert pkt[2] == 0x01  # second byte of remaining length

        # Variable header starts at offset 3 (after 1-byte fixed header + 2-byte remaining length)
        parsed_packet_id = struct.unpack_from('!H', pkt, 3)[0]
        assert parsed_packet_id == packet_id

        # Payload starts at offset 5
        for i in range(num_topics):
            assert pkt[5 + i] == granted_qos[i], (
                "QoS mismatch at index %d: expected %d, got %d" % (i, granted_qos[i], pkt[5 + i])
            )

        # Verify total packet length: 1 (type) + 2 (remaining length) + 2 (packet_id) + 130 (qos)
        assert len(pkt) == 1 + 2 + 2 + num_topics


class TestUnsubackPacket:
    """Test UNSUBACK packet building."""

    def test_build_unsuback(self):
        """Test building UNSUBACK packet."""
        pkt = build_unsuback(50)
        assert pkt == bytes([0xB0, 0x02]) + struct.pack('!H', 50)


class TestPingrespPacket:
    """Test PINGRESP constant."""

    def test_pingresp_bytes(self):
        """Test PINGRESP packet constant."""
        assert PINGRESP_BYTES == bytes([0xD0, 0x00])


class TestReadPacket:
    """Test read_packet() from asyncio StreamReader."""

    @pytest.mark.asyncio
    async def test_read_connect_packet(self):
        """Test reading a CONNECT packet."""
        from conftest import MockReader

        # Build CONNECT packet
        payload = bytearray()
        payload.extend(encode_utf8_string(b'MQTT'))
        payload.append(4)
        payload.append(0x02)  # clean_session
        payload.extend(struct.pack('!H', 60))
        payload.extend(encode_utf8_string('test-client'))

        data = bytearray([0x10])  # CONNECT type
        data.append(len(payload))
        data.extend(payload)

        reader = MockReader(bytes(data))
        pkt_type, flags, pkt_data = await packet.read_packet(reader)

        assert pkt_type == packet.CONNECT
        assert flags == 0
        assert pkt_data == bytes(payload)

    @pytest.mark.asyncio
    async def test_read_publish_packet(self):
        """Test reading a PUBLISH packet."""
        from conftest import MockReader

        pub = build_publish(b'test/topic', b'hello', qos=0, retain=False)
        reader = MockReader(pub)
        pkt_type, flags, pkt_data = await packet.read_packet(reader)

        assert pkt_type == packet.PUBLISH
        assert (flags & 0x01) == 0  # retain=False

    @pytest.mark.asyncio
    async def test_read_pingreq_packet(self):
        """Test reading a PINGREQ packet."""
        from conftest import MockReader

        reader = MockReader(bytes([0xC0, 0x00]))
        pkt_type, flags, pkt_data = await packet.read_packet(reader)

        assert pkt_type == packet.PINGREQ
        assert flags == 0
        assert pkt_data == b''

    @pytest.mark.asyncio
    async def test_read_disconnect_packet(self):
        """Test reading a DISCONNECT packet."""
        from conftest import MockReader

        reader = MockReader(bytes([0xE0, 0x00]))
        pkt_type, flags, pkt_data = await packet.read_packet(reader)

        assert pkt_type == packet.DISCONNECT
        assert pkt_data == b''

    @pytest.mark.asyncio
    async def test_read_multi_byte_remaining_length(self):
        """Test reading packet with multi-byte remaining length."""
        from conftest import MockReader

        # Build a PUBLISH with payload > 127 bytes (needs 2-byte remaining length)
        topic = b'test'
        payload = b'x' * 200

        pub = build_publish(topic, payload, qos=0)
        reader = MockReader(pub)
        pkt_type, flags, pkt_data = await packet.read_packet(reader)

        assert pkt_type == packet.PUBLISH
        parsed = parse_publish(pkt_data, flags)
        assert parsed.payload == payload

    @pytest.mark.asyncio
    async def test_read_remaining_length_overflow(self):
        """Test read_packet rejects remaining length > 4 bytes."""
        from conftest import MockReader

        # Build data with remaining length that exceeds 4 bytes
        # Continuation bits set for 5 bytes: 0x80, 0x80, 0x80, 0x80, 0x01
        data = bytes([0x30, 0x80, 0x80, 0x80, 0x80, 0x01])
        reader = MockReader(data)

        with pytest.raises(MQTTProtocolError, match="Remaining length"):
            await packet.read_packet(reader)

    @pytest.mark.asyncio
    async def test_read_incomplete_data(self):
        """Test read_packet raises on incomplete data."""
        import asyncio
        from conftest import MockReader

        # Only first byte, no remaining length
        reader = MockReader(bytes([0x30]))

        with pytest.raises(asyncio.IncompleteReadError):
            await packet.read_packet(reader)
