"""Tests for beehivemqtt.qos module."""

import pytest
from beehivemqtt.qos import QoS1Outbound, QoS2Inbound, QoS2Outbound, QoSManager
from beehivemqtt.session import ClientSession
from beehivemqtt.config import BrokerConfig


class TestQoS1Outbound:
    """Test QoS1Outbound tracking class."""

    def test_initialization(self):
        """Test QoS1Outbound initialization."""
        entry = QoS1Outbound(packet_id=42, topic=b'test/topic', payload=b'payload', qos=1)

        assert entry.packet_id == 42
        assert entry.topic == b'test/topic'
        assert entry.payload == b'payload'
        assert entry.qos == 1
        assert entry.retry_count == 0
        assert entry.timestamp == 0


class TestQoS2Inbound:
    """Test QoS2Inbound tracking class."""

    def test_initialization(self):
        """Test QoS2Inbound initialization."""
        entry = QoS2Inbound(packet_id=100, topic=b'topic', payload=b'data', retain=True)

        assert entry.packet_id == 100
        assert entry.topic == b'topic'
        assert entry.payload == b'data'
        assert entry.retain is True
        assert entry.state == QoS2Inbound.PUBREC_SENT
        assert entry.timestamp == 0


class TestQoS2Outbound:
    """Test QoS2Outbound tracking class."""

    def test_initialization(self):
        """Test QoS2Outbound initialization."""
        entry = QoS2Outbound(packet_id=200, topic=b'topic', payload=b'payload')

        assert entry.packet_id == 200
        assert entry.topic == b'topic'
        assert entry.payload == b'payload'
        assert entry.state == QoS2Outbound.AWAITING_PUBREC
        assert entry.retry_count == 0
        assert entry.timestamp == 0


class TestQoSManager:
    """Test QoSManager class."""

    @pytest.fixture
    def qos_manager(self, broker_config):
        """Provide QoSManager instance."""
        return QoSManager(broker_config)

    @pytest.fixture
    def session(self):
        """Provide a test session."""
        return ClientSession('test-client')

    def test_track_outbound_qos1(self, qos_manager, session):
        """Test tracking outbound QoS 1 message."""
        entry = qos_manager.track_outbound_qos1(
            session, packet_id=1, topic=b'test', payload=b'data', qos=1
        )

        assert entry.packet_id == 1
        assert entry.topic == b'test'
        assert entry.payload == b'data'
        assert entry.qos == 1
        assert entry.timestamp > 0
        assert 1 in session.pending_qos1

    def test_handle_puback_removes_entry(self, qos_manager, session):
        """Test handle_puback removes QoS 1 entry."""
        qos_manager.track_outbound_qos1(session, 1, b'topic', b'payload', 1)

        result = qos_manager.handle_puback(session, 1)

        assert result is True
        assert 1 not in session.pending_qos1

    def test_handle_puback_unknown_packet_id(self, qos_manager, session):
        """Test handle_puback with unknown packet_id returns False."""
        result = qos_manager.handle_puback(session, 999)
        assert result is False

    def test_track_inbound_qos2(self, qos_manager, session):
        """Test tracking inbound QoS 2 message."""
        entry = qos_manager.track_inbound_qos2(
            session, packet_id=2, topic=b'test', payload=b'data', retain=False
        )

        assert entry.packet_id == 2
        assert entry.state == QoS2Inbound.PUBREC_SENT
        assert entry.timestamp > 0
        assert 2 in session.pending_qos2

    def test_handle_pubrel_returns_message(self, qos_manager, session):
        """Test handle_pubrel returns message data."""
        qos_manager.track_inbound_qos2(session, 2, b'topic', b'payload', retain=True)

        result = qos_manager.handle_pubrel(session, 2)

        assert result is not None
        assert result == (b'topic', b'payload', True)
        # Entry should still exist but state changed
        assert 2 in session.pending_qos2
        assert session.pending_qos2[2].state == QoS2Inbound.PUBCOMP_SENT

    def test_handle_pubrel_unknown_packet_id(self, qos_manager, session):
        """Test handle_pubrel with unknown packet_id returns None."""
        result = qos_manager.handle_pubrel(session, 999)
        assert result is None

    def test_track_outbound_qos2(self, qos_manager, session):
        """Test tracking outbound QoS 2 message."""
        entry = qos_manager.track_outbound_qos2(
            session, packet_id=3, topic=b'test', payload=b'data'
        )

        assert entry.packet_id == 3
        assert entry.state == QoS2Outbound.AWAITING_PUBREC
        assert entry.timestamp > 0
        assert 3 in session.pending_qos2_out

    def test_handle_pubrec_transitions_state(self, qos_manager, session):
        """Test handle_pubrec transitions QoS 2 state."""
        qos_manager.track_outbound_qos2(session, 3, b'topic', b'payload')

        result = qos_manager.handle_pubrec(session, 3)

        assert result is True
        entry = session.pending_qos2_out[3]
        assert entry.state == QoS2Outbound.AWAITING_PUBCOMP
        assert entry.timestamp > 0

    def test_handle_pubrec_wrong_state(self, qos_manager, session):
        """Test handle_pubrec on wrong state returns False."""
        entry = qos_manager.track_outbound_qos2(session, 3, b'topic', b'payload')
        entry.state = QoS2Outbound.AWAITING_PUBCOMP  # Already transitioned

        result = qos_manager.handle_pubrec(session, 3)

        assert result is False

    def test_handle_pubrec_not_qos2_entry(self, qos_manager, session):
        """Test handle_pubrec on QoS 1 entry returns False."""
        qos_manager.track_outbound_qos1(session, 1, b'topic', b'payload', 1)

        result = qos_manager.handle_pubrec(session, 1)

        assert result is False

    def test_handle_pubcomp_removes_outbound_qos2(self, qos_manager, session):
        """Test handle_pubcomp removes outbound QoS 2 entry."""
        qos_manager.track_outbound_qos2(session, 3, b'topic', b'payload')

        result = qos_manager.handle_pubcomp(session, 3)

        assert result is True
        assert 3 not in session.pending_qos2_out

    def test_handle_pubcomp_removes_inbound_qos2(self, qos_manager, session):
        """Test handle_pubcomp removes inbound QoS 2 entry."""
        qos_manager.track_inbound_qos2(session, 2, b'topic', b'payload', False)
        session.pending_qos2[2].state = QoS2Inbound.PUBCOMP_SENT

        result = qos_manager.handle_pubcomp(session, 2)

        assert result is True
        assert 2 not in session.pending_qos2

    def test_get_inflight_count(self, qos_manager, session):
        """Test get_inflight_count returns total of QoS 1 and 2."""
        qos_manager.track_outbound_qos1(session, 1, b'topic1', b'data1', 1)
        qos_manager.track_outbound_qos1(session, 2, b'topic2', b'data2', 1)
        qos_manager.track_inbound_qos2(session, 10, b'topic3', b'data3', False)
        qos_manager.track_inbound_qos2(session, 11, b'topic4', b'data4', False)

        count = qos_manager.get_inflight_count(session)

        assert count == 4

    def test_get_inflight_count_empty(self, qos_manager, session):
        """Test get_inflight_count on empty session."""
        count = qos_manager.get_inflight_count(session)
        assert count == 0

    @pytest.mark.asyncio
    async def test_retransmit_pending_does_not_retransmit_recent(self, qos_manager, client_session):
        """Test retransmit_pending does not retransmit recent messages."""
        qos_manager.track_outbound_qos1(client_session, 1, b'topic', b'payload', 1)

        # Clear writer data
        client_session.writer.clear()

        # Retransmit (should not send anything since message is recent)
        await qos_manager.retransmit_pending(client_session)

        # No data should be written
        assert len(client_session.writer.get_data()) == 0

    @pytest.mark.asyncio
    async def test_retransmit_pending_retransmits_old_qos1(self, qos_manager, broker_config, client_session):
        """Test retransmit_pending retransmits old QoS 1 messages."""
        import time

        # Set very short retry interval for testing
        broker_config.qos_retry_interval = 0.001  # 1ms

        entry = qos_manager.track_outbound_qos1(client_session, 1, b'topic', b'payload', 1)
        # Make it old
        entry.timestamp = time.ticks_ms() - 1000

        client_session.writer.clear()

        # Retransmit
        await qos_manager.retransmit_pending(client_session)

        # Should have retransmitted
        assert len(client_session.writer.get_data()) > 0
        assert entry.retry_count == 1

    @pytest.mark.asyncio
    async def test_retransmit_pending_removes_after_max_retries(self, qos_manager, broker_config, client_session):
        """Test retransmit_pending removes entry after max retries."""
        import time

        broker_config.qos_retry_interval = 0.001
        broker_config.qos_max_retries = 2

        entry = qos_manager.track_outbound_qos1(client_session, 1, b'topic', b'payload', 1)
        entry.timestamp = time.ticks_ms() - 1000
        entry.retry_count = 2  # Already at max

        await qos_manager.retransmit_pending(client_session)

        # Entry should be removed
        assert 1 not in client_session.pending_qos1
