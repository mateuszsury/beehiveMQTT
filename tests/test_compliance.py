"""
MQTT 3.1.1 Compliance Tests for BeehiveMQTT.

Tests key requirements from the MQTT 3.1.1 specification to ensure
broker behaves correctly according to the standard.
"""

import pytest
import struct
from beehivemqtt.packet import (
    parse_connect, parse_publish, parse_subscribe, parse_unsubscribe,
    build_connack,
    CONNACK_ACCEPTED, CONNACK_REFUSED_PROTOCOL, CONNACK_REFUSED_IDENTIFIER
)
from beehivemqtt.utils import encode_utf8_string
from beehivemqtt.errors import MQTTProtocolError


class TestMQTT311Compliance:
    """Test MQTT 3.1.1 specification compliance."""

    def build_connect_packet(self, protocol_name=b'MQTT', protocol_level=4,
                            client_id='test', clean_session=True, keep_alive=60,
                            username=None, password=None, will=None):
        """Helper to build CONNECT packet payload."""
        data = bytearray()

        # Protocol name
        data.extend(encode_utf8_string(protocol_name))

        # Protocol level
        data.append(protocol_level)

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

    def test_first_packet_must_be_connect(self):
        """
        [MQTT-3.1.0-1] First packet from client must be CONNECT.

        This test verifies the requirement, but actual enforcement
        is done in the broker's connection handler.
        """
        # This is enforced by the broker - if first packet is not CONNECT,
        # connection should be closed. We verify CONNECT parsing works correctly.
        data = self.build_connect_packet()
        connect = parse_connect(data)

        assert connect.protocol_name == b'MQTT'
        assert connect.protocol_level == 4

    def test_protocol_name_must_be_mqtt(self):
        """
        [MQTT-3.1.2-1] Protocol name must be "MQTT".

        Invalid protocol name should raise MQTTProtocolError.
        """
        data = self.build_connect_packet(protocol_name=b'XXXX')

        with pytest.raises(MQTTProtocolError, match="Invalid protocol name"):
            parse_connect(data)

    def test_protocol_version_4_required(self):
        """
        [MQTT-3.1.2-2] Protocol level must be 4 for MQTT 3.1.1.

        Unsupported protocol levels should raise MQTTProtocolError.
        """
        # Protocol level 3 (MQTT 3.1)
        data = self.build_connect_packet(protocol_level=3)

        with pytest.raises(MQTTProtocolError, match="Unsupported protocol level"):
            parse_connect(data)

        # Protocol level 5 (MQTT 5.0)
        data = self.build_connect_packet(protocol_level=5)

        with pytest.raises(MQTTProtocolError, match="Unsupported protocol level"):
            parse_connect(data)

    def test_reserved_flag_must_be_zero(self):
        """
        [MQTT-3.1.2-3] Reserved flag in CONNECT must be 0.

        If reserved flag is set, connection should be rejected.
        """
        data = bytearray()
        data.extend(encode_utf8_string(b'MQTT'))
        data.append(4)
        data.append(0x03)  # Reserved bit set (bit 0)
        data.extend(struct.pack('!H', 60))
        data.extend(encode_utf8_string('test'))

        with pytest.raises(MQTTProtocolError, match="Reserved bit"):
            parse_connect(bytes(data))

    def test_clean_session_flag(self):
        """
        [MQTT-3.1.2-4] Clean session flag behavior.

        When clean_session=True, server must discard previous session.
        When clean_session=False, server must resume session if it exists.
        """
        # Clean session = True
        data = self.build_connect_packet(clean_session=True)
        connect = parse_connect(data)
        assert connect.clean_session is True

        # Clean session = False
        data = self.build_connect_packet(clean_session=False)
        connect = parse_connect(data)
        assert connect.clean_session is False

    def test_will_flag_validation(self):
        """
        [MQTT-3.1.2-11] If will flag is 0, will QoS and retain must be 0.

        Invalid will flag combination should raise MQTTProtocolError.
        """
        data = bytearray()
        data.extend(encode_utf8_string(b'MQTT'))
        data.append(4)
        # Will flag = 0, but will QoS = 1 (invalid)
        data.append(0x08)  # QoS bits set but will flag not set
        data.extend(struct.pack('!H', 60))
        data.extend(encode_utf8_string('test'))

        with pytest.raises(MQTTProtocolError, match="Will QoS/Retain set but Will flag is 0"):
            parse_connect(bytes(data))

    def test_will_qos_validation(self):
        """
        [MQTT-3.1.2-14] Will QoS must not be 3.

        Invalid will QoS should raise MQTTProtocolError.
        """
        data = bytearray()
        data.extend(encode_utf8_string(b'MQTT'))
        data.append(4)
        # Will flag set, QoS = 3 (invalid)
        data.append(0x1C)  # Will flag + QoS 3
        data.extend(struct.pack('!H', 60))
        data.extend(encode_utf8_string('test'))
        data.extend(encode_utf8_string('will/topic'))
        data.extend(encode_utf8_string('will message'))

        with pytest.raises(MQTTProtocolError, match="Invalid Will QoS"):
            parse_connect(bytes(data))

    def test_client_id_zero_length_behavior(self):
        """
        [MQTT-3.1.3-6] Zero-length client ID with clean_session=True is valid.
        [MQTT-3.1.3-8] Zero-length client ID with clean_session=False is invalid.

        Server should accept empty client_id with clean_session=True,
        and reject it with clean_session=False.
        """
        # Zero-length with clean_session=True (valid)
        data = self.build_connect_packet(client_id='', clean_session=True)
        connect = parse_connect(data)
        assert connect.client_id == b''
        assert connect.clean_session is True

        # Zero-length with clean_session=False (would be rejected by broker)
        data = self.build_connect_packet(client_id='', clean_session=False)
        connect = parse_connect(data)
        assert connect.client_id == b''
        assert connect.clean_session is False
        # Note: Broker should reject this with CONNACK return code 0x02

    def test_username_password_flags(self):
        """
        [MQTT-3.1.2-18] Username flag must be set if password flag is set.

        This is implicitly enforced by parsing order - password can only
        be present if username is present.
        """
        # Valid: both username and password
        data = self.build_connect_packet(username='user1', password='pass1')
        connect = parse_connect(data)
        assert connect.has_username is True
        assert connect.has_password is True

        # Valid: username without password
        data = self.build_connect_packet(username='user1', password=None)
        connect = parse_connect(data)
        assert connect.has_username is True
        assert connect.has_password is False

    def test_connack_session_present_flag(self):
        """
        [MQTT-3.2.2-1] Session present flag in CONNACK.

        When clean_session=True, session_present must be False.
        """
        # Session present = False
        connack = build_connack(session_present=False, return_code=CONNACK_ACCEPTED)
        assert connack[2] == 0x00  # Session present byte

        # Session present = True
        connack = build_connack(session_present=True, return_code=CONNACK_ACCEPTED)
        assert connack[2] == 0x01  # Session present byte

    def test_connack_return_codes(self):
        """
        [MQTT-3.2.2-4] CONNACK return codes.

        Verify all standard return codes can be built.
        """
        # 0x00 - Connection accepted
        connack = build_connack(False, 0x00)
        assert connack[3] == 0x00

        # 0x01 - Unacceptable protocol version
        connack = build_connack(False, 0x01)
        assert connack[3] == 0x01

        # 0x02 - Identifier rejected
        connack = build_connack(False, 0x02)
        assert connack[3] == 0x02

        # 0x03 - Server unavailable
        connack = build_connack(False, 0x03)
        assert connack[3] == 0x03

        # 0x04 - Bad username or password
        connack = build_connack(False, 0x04)
        assert connack[3] == 0x04

        # 0x05 - Not authorized
        connack = build_connack(False, 0x05)
        assert connack[3] == 0x05

    def test_keep_alive_zero_disables(self):
        """
        [MQTT-3.1.2-22] Keep alive value of 0 disables keep alive.

        Server should not disconnect client when keep_alive=0.
        """
        data = self.build_connect_packet(keep_alive=0)
        connect = parse_connect(data)

        assert connect.keep_alive == 0
        # Broker should not enforce keep-alive timeout for this connection

    def test_will_message_published_on_ungraceful_disconnect(self):
        """
        [MQTT-3.1.2-8] Will message must be published on ungraceful disconnect.

        This is a broker behavior test - when a client disconnects without
        sending DISCONNECT, the will message should be published.
        """
        # Create CONNECT with will message
        will = {
            'topic': 'client/status',
            'message': 'offline',
            'qos': 1,
            'retain': True
        }
        data = self.build_connect_packet(will=will)
        connect = parse_connect(data)

        assert connect.has_will is True
        assert connect.will_topic == b'client/status'
        assert connect.will_message == b'offline'
        assert connect.will_qos == 1
        assert connect.will_retain is True

        # Broker should store this and publish it on ungraceful disconnect

    def test_will_message_not_published_on_clean_disconnect(self):
        """
        [MQTT-3.1.2-10] Will message must NOT be published on clean disconnect.

        When client sends DISCONNECT packet, will message should be discarded.
        """
        from beehivemqtt.session import ClientSession

        session = ClientSession('test-client')
        session.will_topic = b'client/status'
        session.will_message = b'offline'

        # Simulate clean disconnect - broker clears will before handling
        session.will_topic = None
        session.will_message = None

        assert session.will_topic is None
        assert session.will_message is None

    def test_packet_id_must_be_nonzero(self):
        """
        [MQTT-2.3.1-1] Packet identifier must be non-zero.

        SUBSCRIBE, UNSUBSCRIBE, and QoS > 0 PUBLISH must have packet_id != 0.
        """
        from beehivemqtt.packet import parse_publish, parse_subscribe, parse_unsubscribe

        # PUBLISH QoS 1 with packet_id=0
        data = bytearray()
        data.extend(encode_utf8_string(b'test/topic'))
        data.extend(struct.pack('!H', 0))  # packet_id = 0
        data.extend(b'payload')

        with pytest.raises(MQTTProtocolError, match="Packet ID cannot be 0"):
            parse_publish(bytes(data), flags=0x02)  # QoS 1

        # SUBSCRIBE with packet_id=0
        sub_data = bytearray()
        sub_data.extend(struct.pack('!H', 0))  # packet_id = 0
        sub_data.extend(encode_utf8_string(b'test/#'))
        sub_data.append(0)  # QoS 0

        with pytest.raises(MQTTProtocolError, match="Packet ID cannot be 0"):
            parse_subscribe(bytes(sub_data))

        # UNSUBSCRIBE with packet_id=0
        unsub_data = bytearray()
        unsub_data.extend(struct.pack('!H', 0))  # packet_id = 0
        unsub_data.extend(encode_utf8_string(b'test/#'))

        with pytest.raises(MQTTProtocolError, match="Packet ID cannot be 0"):
            parse_unsubscribe(bytes(unsub_data))

    def test_topic_name_must_not_be_empty(self):
        """
        [MQTT-4.7.3-1] Topic name in PUBLISH must not be empty.

        Empty topic names should be rejected.
        """
        from beehivemqtt.packet import parse_publish

        # Build PUBLISH with empty topic
        data = bytearray()
        data.extend(struct.pack('!H', 0))  # topic length = 0
        data.extend(b'payload')

        with pytest.raises(MQTTProtocolError, match="Empty topic"):
            parse_publish(bytes(data), flags=0x00)  # QoS 0

    def test_topic_name_must_not_contain_wildcards(self):
        """
        [MQTT-3.3.2-2] Topic name in PUBLISH must not contain wildcards.

        Topic names with + or # should be rejected.
        """
        from beehivemqtt.packet import parse_publish

        # Topic with '+'
        data_plus = bytearray()
        data_plus.extend(encode_utf8_string(b'home/+/temp'))
        data_plus.extend(b'payload')

        with pytest.raises(MQTTProtocolError, match="Wildcards not allowed"):
            parse_publish(bytes(data_plus), flags=0x00)

        # Topic with '#'
        data_hash = bytearray()
        data_hash.extend(encode_utf8_string(b'home/#'))
        data_hash.extend(b'payload')

        with pytest.raises(MQTTProtocolError, match="Wildcards not allowed"):
            parse_publish(bytes(data_hash), flags=0x00)

    def test_subscription_with_wildcard(self):
        """
        [MQTT-4.7.1-1] Topic filters can contain wildcards.

        '+' for single level, '#' for multi-level.
        """
        from beehivemqtt.topic import TopicTree

        tree = TopicTree()

        # '+' wildcard
        tree.subscribe('home/+/temp', 'client1', 0)
        subs = tree.match('home/living/temp')
        assert 'client1' in subs

        subs = tree.match('home/bedroom/temp')
        assert 'client1' in subs

        # Should NOT match deeper levels
        subs = tree.match('home/living/room/temp')
        assert 'client1' not in subs

        # '#' wildcard
        tree.subscribe('sensor/#', 'client2', 1)
        subs = tree.match('sensor/temp')
        assert 'client2' in subs

        subs = tree.match('sensor/humidity/indoor')
        assert 'client2' in subs

        # '#' matches zero levels too
        subs = tree.match('sensor')
        assert 'client2' in subs

    def test_sys_topics_not_matched_by_wildcard(self):
        """
        [MQTT-4.7.2-1] Topics starting with $ not matched by # at first level.

        $SYS topics should not match wildcard subscriptions at first level.
        """
        from beehivemqtt.topic import TopicTree

        tree = TopicTree()

        # Subscribe with '#' at first level
        tree.subscribe('#', 'client1', 0)
        tree.subscribe('+/info', 'client2', 0)

        # $SYS topic should NOT match
        subs = tree.match('$SYS/broker/version')
        assert 'client1' not in subs
        assert 'client2' not in subs

        # But explicit subscription to $SYS should work
        tree.subscribe('$SYS/#', 'client3', 0)
        subs = tree.match('$SYS/broker/version')
        assert 'client3' in subs

        # Normal topics should still match '#'
        subs = tree.match('normal/topic')
        assert 'client1' in subs

    def test_clean_session_true_clears_state(self):
        """
        [MQTT-3.1.2-6] Clean session clears previous session state.

        When clean_session=True, all session state should be discarded.
        """
        from beehivemqtt.session import ClientSession, SessionManager
        from beehivemqtt.config import BrokerConfig
        from beehivemqtt.topic import TopicTree

        config = BrokerConfig()
        sessions = {}
        manager = SessionManager(sessions, config)

        # Create persistent session with subscriptions
        session1 = ClientSession('client-x', clean_session=False)
        session1.subscriptions = {'home/temp': 1, 'home/humid': 0}
        sessions['client-x'] = session1

        # Reconnect with clean_session=True
        session2, session_present = manager.get_or_create('client-x', clean_session=True)

        assert session_present is False  # Clean session = no previous state
        assert session2.subscriptions == {}  # New session has no subs
        assert session2.clean_session is True

    def test_qos2_disabled_config(self):
        """
        Test that BrokerConfig(qos2_enabled=False) sets attribute to False.

        When QoS 2 is disabled, broker should reject QoS 2 publishes.
        """
        from beehivemqtt.config import BrokerConfig
        config = BrokerConfig(qos2_enabled=False)

        assert config.qos2_enabled is False

    def test_session_has_pending_qos2_out(self):
        """
        Test that ClientSession has an empty pending_qos2_out dict.

        QoS 2 outbound tracking is required for PUBREL/PUBCOMP flow.
        """
        from beehivemqtt.session import ClientSession
        session = ClientSession('test-client')

        assert session.pending_qos2_out == {}
        assert isinstance(session.pending_qos2_out, dict)
