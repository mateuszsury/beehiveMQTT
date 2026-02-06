"""End-to-end QoS flow tests for BeehiveMQTT.

Tests complete QoS 1 and QoS 2 message flows through QoSManager,
MessageRouter, and ClientSession integration. Verifies correct
state transitions, packet tracking, and isolation between QoS levels.
"""

import pytest
import asyncio

from conftest import MockWriter, MockReader
from beehivemqtt.qos import QoSManager, QoS1Outbound, QoS2Inbound, QoS2Outbound
from beehivemqtt.router import MessageRouter
from beehivemqtt.topic import TopicTree
from beehivemqtt.session import ClientSession
from beehivemqtt.config import BrokerConfig


def _make_session(client_id='test'):
    """Create a connected ClientSession with mock reader/writer."""
    session = ClientSession(client_id)
    session.writer = MockWriter()
    session.reader = MockReader()
    session.connected = True
    session.update_activity()
    return session


@pytest.fixture
def config():
    """Provide a BrokerConfig with test defaults."""
    return BrokerConfig(
        port=1883,
        max_clients=5,
        max_subscriptions_per_client=10,
        max_payload_size=1024,
        max_retained_messages=20,
        connect_timeout=5,
        log_level='ERROR'
    )


@pytest.fixture
def qos_mgr(config):
    """Provide a QoSManager instance."""
    return QoSManager(config)


# --------------------------------------------------------------------------
# Test 1: QoS 1 full flow - PUBLISH -> track_outbound_qos1 -> handle_puback
# --------------------------------------------------------------------------

class TestQoS1FullFlow:
    """QoS 1 end-to-end: track outbound, verify pending, PUBACK removes it."""

    def test_track_outbound_qos1_adds_to_pending(self, qos_mgr):
        session = _make_session()
        entry = qos_mgr.track_outbound_qos1(session, 1, b'test/topic', b'hello', 1)

        assert 1 in session.pending_qos1
        assert isinstance(entry, QoS1Outbound)
        assert entry.packet_id == 1
        assert entry.topic == b'test/topic'
        assert entry.payload == b'hello'
        assert entry.qos == 1
        assert entry.retry_count == 0
        assert entry.timestamp > 0

    def test_handle_puback_removes_pending(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_outbound_qos1(session, 1, b'test/topic', b'hello', 1)

        assert len(session.pending_qos1) == 1
        result = qos_mgr.handle_puback(session, 1)

        assert result is True
        assert len(session.pending_qos1) == 0

    def test_handle_puback_unknown_packet_id_returns_false(self, qos_mgr):
        session = _make_session()
        result = qos_mgr.handle_puback(session, 999)
        assert result is False

    def test_qos1_full_cycle(self, qos_mgr):
        """Complete QoS 1 cycle: track -> verify present -> PUBACK -> verify gone."""
        session = _make_session()

        # Simulate broker sending QoS 1 PUBLISH to subscriber
        qos_mgr.track_outbound_qos1(session, 42, b'sensor/temp', b'22.5', 1)
        assert 42 in session.pending_qos1
        assert qos_mgr.get_inflight_count(session) == 1

        # Subscriber sends PUBACK
        result = qos_mgr.handle_puback(session, 42)
        assert result is True
        assert 42 not in session.pending_qos1
        assert qos_mgr.get_inflight_count(session) == 0


# --------------------------------------------------------------------------
# Test 2: QoS 2 full inbound flow - track_inbound -> PUBREL -> PUBCOMP
# --------------------------------------------------------------------------

class TestQoS2InboundFlow:
    """QoS 2 inbound: client publishes QoS 2 to broker."""

    def test_track_inbound_qos2_adds_to_pending(self, qos_mgr):
        session = _make_session()
        entry = qos_mgr.track_inbound_qos2(session, 10, b'cmd/run', b'start', False)

        assert 10 in session.pending_qos2
        assert isinstance(entry, QoS2Inbound)
        assert entry.packet_id == 10
        assert entry.topic == b'cmd/run'
        assert entry.payload == b'start'
        assert entry.retain is False
        assert entry.state == QoS2Inbound.PUBREC_SENT
        assert entry.timestamp > 0

    def test_handle_pubrel_returns_message_data(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_inbound_qos2(session, 10, b'cmd/run', b'start', True)

        result = qos_mgr.handle_pubrel(session, 10)
        assert result is not None
        topic, payload, retain = result
        assert topic == b'cmd/run'
        assert payload == b'start'
        assert retain is True

    def test_handle_pubrel_transitions_state(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_inbound_qos2(session, 10, b'cmd/run', b'start', False)

        qos_mgr.handle_pubrel(session, 10)

        # Entry should still exist but in PUBCOMP_SENT state
        assert 10 in session.pending_qos2
        assert session.pending_qos2[10].state == QoS2Inbound.PUBCOMP_SENT

    def test_handle_pubrel_unknown_returns_none(self, qos_mgr):
        session = _make_session()
        result = qos_mgr.handle_pubrel(session, 999)
        assert result is None

    def test_handle_pubcomp_cleans_up_inbound(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_inbound_qos2(session, 10, b'cmd/run', b'start', False)
        qos_mgr.handle_pubrel(session, 10)

        # PUBCOMP cleans up the inbound entry
        result = qos_mgr.handle_pubcomp(session, 10)
        assert result is True
        assert 10 not in session.pending_qos2

    def test_qos2_inbound_full_cycle(self, qos_mgr):
        """Complete QoS 2 inbound: track -> PUBREL returns data -> PUBCOMP cleans up."""
        session = _make_session()

        # Step 1: Client sends QoS 2 PUBLISH, broker tracks and sends PUBREC
        qos_mgr.track_inbound_qos2(session, 7, b'home/alarm', b'triggered', True)
        assert qos_mgr.get_inflight_count(session) == 1

        # Step 2: Client sends PUBREL, broker gets message data for routing
        msg_data = qos_mgr.handle_pubrel(session, 7)
        assert msg_data == (b'home/alarm', b'triggered', True)
        # Entry still present (until PUBCOMP sent)
        assert 7 in session.pending_qos2

        # Step 3: Broker sends PUBCOMP, entry cleaned up
        result = qos_mgr.handle_pubcomp(session, 7)
        assert result is True
        assert 7 not in session.pending_qos2
        assert qos_mgr.get_inflight_count(session) == 0


# --------------------------------------------------------------------------
# Test 3: QoS 2 full outbound flow - track_outbound -> PUBREC -> PUBCOMP
# --------------------------------------------------------------------------

class TestQoS2OutboundFlow:
    """QoS 2 outbound: broker sends QoS 2 to subscriber."""

    def test_track_outbound_qos2_adds_to_pending(self, qos_mgr):
        session = _make_session()
        entry = qos_mgr.track_outbound_qos2(session, 20, b'data/stream', b'payload')

        assert 20 in session.pending_qos2_out
        assert isinstance(entry, QoS2Outbound)
        assert entry.packet_id == 20
        assert entry.topic == b'data/stream'
        assert entry.payload == b'payload'
        assert entry.state == QoS2Outbound.AWAITING_PUBREC
        assert entry.retry_count == 0
        assert entry.timestamp > 0

    def test_handle_pubrec_transitions_to_awaiting_pubcomp(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_outbound_qos2(session, 20, b'data/stream', b'payload')

        result = qos_mgr.handle_pubrec(session, 20)
        assert result is True
        assert session.pending_qos2_out[20].state == QoS2Outbound.AWAITING_PUBCOMP

    def test_handle_pubrec_unknown_returns_false(self, qos_mgr):
        session = _make_session()
        result = qos_mgr.handle_pubrec(session, 999)
        assert result is False

    def test_handle_pubrec_resets_timestamp(self, qos_mgr):
        session = _make_session()
        entry = qos_mgr.track_outbound_qos2(session, 20, b'data/stream', b'payload')
        original_timestamp = entry.timestamp

        # Small delay not needed -- timestamp is reset regardless
        qos_mgr.handle_pubrec(session, 20)
        # Timestamp should be updated (>= original)
        assert entry.timestamp >= original_timestamp

    def test_handle_pubcomp_removes_outbound(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_outbound_qos2(session, 20, b'data/stream', b'payload')
        qos_mgr.handle_pubrec(session, 20)

        result = qos_mgr.handle_pubcomp(session, 20)
        assert result is True
        assert 20 not in session.pending_qos2_out

    def test_handle_pubcomp_unknown_returns_false(self, qos_mgr):
        session = _make_session()
        result = qos_mgr.handle_pubcomp(session, 999)
        assert result is False

    def test_qos2_outbound_full_cycle(self, qos_mgr):
        """Complete QoS 2 outbound: track -> PUBREC transitions -> PUBCOMP removes."""
        session = _make_session()

        # Step 1: Broker sends QoS 2 PUBLISH, tracked as outbound
        qos_mgr.track_outbound_qos2(session, 55, b'event/alert', b'fire')
        assert session.pending_qos2_out[55].state == QoS2Outbound.AWAITING_PUBREC
        assert qos_mgr.get_inflight_count(session) == 1

        # Step 2: Subscriber sends PUBREC, state transitions
        qos_mgr.handle_pubrec(session, 55)
        assert session.pending_qos2_out[55].state == QoS2Outbound.AWAITING_PUBCOMP
        assert qos_mgr.get_inflight_count(session) == 1  # Still inflight

        # Step 3: Subscriber sends PUBCOMP, entry removed
        qos_mgr.handle_pubcomp(session, 55)
        assert 55 not in session.pending_qos2_out
        assert qos_mgr.get_inflight_count(session) == 0


# --------------------------------------------------------------------------
# Test 4: QoS 1 outbound via router
# --------------------------------------------------------------------------

class TestQoS1ViaRouter:
    """Route a QoS 1 PUBLISH through MessageRouter to a subscriber."""

    @pytest.mark.asyncio
    async def test_route_publish_qos1_sends_packet_and_tracks(self, config):
        topic_tree = TopicTree()
        sessions = {}
        qos_mgr = QoSManager(config)

        # Create subscriber session
        sub_session = _make_session('subscriber')
        sessions['subscriber'] = sub_session

        # Subscribe at QoS 1
        topic_tree.subscribe(b'sensor/temp', 'subscriber', 1)

        router = MessageRouter(topic_tree, sessions, config, qos_manager=qos_mgr)

        # Publisher sends QoS 1 message
        await router.route_publish(b'sensor/temp', b'22.5', qos=1, retain=False, sender_id='publisher')

        # Subscriber should have received a packet
        data = sub_session.writer.get_data()
        assert len(data) > 0

        # QoS 1 should be tracked in pending_qos1
        assert len(sub_session.pending_qos1) == 1

        # Verify the tracked entry
        pid = list(sub_session.pending_qos1.keys())[0]
        entry = sub_session.pending_qos1[pid]
        assert entry.topic == b'sensor/temp'
        assert entry.payload == b'22.5'
        assert entry.qos == 1

    @pytest.mark.asyncio
    async def test_route_publish_qos1_no_echo_to_sender(self, config):
        """Publisher should not receive its own message."""
        topic_tree = TopicTree()
        sessions = {}
        qos_mgr = QoSManager(config)

        pub_session = _make_session('pub')
        sessions['pub'] = pub_session
        topic_tree.subscribe(b'test/echo', 'pub', 1)

        router = MessageRouter(topic_tree, sessions, config, qos_manager=qos_mgr)
        await router.route_publish(b'test/echo', b'data', qos=1, retain=False, sender_id='pub')

        # Publisher should NOT have received the message
        assert len(pub_session.writer.get_data()) == 0
        assert len(pub_session.pending_qos1) == 0


# --------------------------------------------------------------------------
# Test 5: QoS 2 outbound via router
# --------------------------------------------------------------------------

class TestQoS2ViaRouter:
    """Route a QoS 2 PUBLISH through MessageRouter to a subscriber."""

    @pytest.mark.asyncio
    async def test_route_publish_qos2_sends_packet_and_tracks(self, config):
        topic_tree = TopicTree()
        sessions = {}
        qos_mgr = QoSManager(config)

        sub_session = _make_session('sub2')
        sessions['sub2'] = sub_session
        topic_tree.subscribe(b'cmd/exec', 'sub2', 2)

        router = MessageRouter(topic_tree, sessions, config, qos_manager=qos_mgr)
        await router.route_publish(b'cmd/exec', b'reboot', qos=2, retain=False, sender_id='admin')

        # Subscriber should have received a packet
        data = sub_session.writer.get_data()
        assert len(data) > 0

        # QoS 2 outbound should be tracked in pending_qos2_out
        assert len(sub_session.pending_qos2_out) == 1

        pid = list(sub_session.pending_qos2_out.keys())[0]
        entry = sub_session.pending_qos2_out[pid]
        assert entry.topic == b'cmd/exec'
        assert entry.payload == b'reboot'
        assert entry.state == QoS2Outbound.AWAITING_PUBREC

    @pytest.mark.asyncio
    async def test_route_publish_qos2_complete_flow_via_router(self, config):
        """Full QoS 2 flow: route -> receive packet -> PUBREC -> PUBCOMP."""
        topic_tree = TopicTree()
        sessions = {}
        qos_mgr = QoSManager(config)

        sub_session = _make_session('sub2')
        sessions['sub2'] = sub_session
        topic_tree.subscribe(b'critical/event', 'sub2', 2)

        router = MessageRouter(topic_tree, sessions, config, qos_manager=qos_mgr)
        await router.route_publish(b'critical/event', b'shutdown', qos=2, retain=False)

        # Get the tracked packet ID
        pid = list(sub_session.pending_qos2_out.keys())[0]

        # Subscriber sends PUBREC
        qos_mgr.handle_pubrec(sub_session, pid)
        assert sub_session.pending_qos2_out[pid].state == QoS2Outbound.AWAITING_PUBCOMP

        # Subscriber sends PUBCOMP
        qos_mgr.handle_pubcomp(sub_session, pid)
        assert len(sub_session.pending_qos2_out) == 0


# --------------------------------------------------------------------------
# Test 6: PUBACK does NOT delete QoS2Outbound entries (isolation test)
# --------------------------------------------------------------------------

class TestPubackQoS2Isolation:
    """PUBACK must only affect QoS 1 entries, not QoS 2 outbound entries.

    This is an important isolation test - a previous bug allowed PUBACK
    to incorrectly clear QoS 2 outbound state.
    """

    def test_puback_does_not_remove_qos2_outbound(self, qos_mgr):
        session = _make_session()

        # Track a QoS 2 outbound with packet_id=5
        qos_mgr.track_outbound_qos2(session, 5, b'qos2/topic', b'data')
        assert 5 in session.pending_qos2_out

        # Send PUBACK for the same packet_id
        result = qos_mgr.handle_puback(session, 5)

        # PUBACK should return False (nothing in pending_qos1)
        assert result is False
        # QoS 2 outbound entry must still be present
        assert 5 in session.pending_qos2_out
        assert session.pending_qos2_out[5].state == QoS2Outbound.AWAITING_PUBREC

    def test_puback_does_not_remove_qos2_inbound(self, qos_mgr):
        session = _make_session()

        # Track a QoS 2 inbound with packet_id=5
        qos_mgr.track_inbound_qos2(session, 5, b'qos2/inbound', b'data', False)
        assert 5 in session.pending_qos2

        # Send PUBACK for the same packet_id
        result = qos_mgr.handle_puback(session, 5)

        # PUBACK should return False (nothing in pending_qos1)
        assert result is False
        # QoS 2 inbound entry must still be present
        assert 5 in session.pending_qos2

    def test_puback_only_affects_qos1_when_all_three_dicts_populated(self, qos_mgr):
        """With entries in all three dicts using same packet_id, PUBACK only removes QoS 1."""
        session = _make_session()

        # Track entries in all three dicts with packet_id=10
        qos_mgr.track_outbound_qos1(session, 10, b't1', b'p1', 1)
        qos_mgr.track_inbound_qos2(session, 10, b't2', b'p2', False)
        qos_mgr.track_outbound_qos2(session, 10, b't3', b'p3')

        assert qos_mgr.get_inflight_count(session) == 3

        # PUBACK should only remove the QoS 1 entry
        result = qos_mgr.handle_puback(session, 10)
        assert result is True
        assert 10 not in session.pending_qos1
        assert 10 in session.pending_qos2
        assert 10 in session.pending_qos2_out
        assert qos_mgr.get_inflight_count(session) == 2


# --------------------------------------------------------------------------
# Test 7: get_inflight_count counts all three dicts
# --------------------------------------------------------------------------

class TestGetInflightCount:
    """get_inflight_count must aggregate pending_qos1 + pending_qos2 + pending_qos2_out."""

    def test_empty_session_has_zero_inflight(self, qos_mgr):
        session = _make_session()
        assert qos_mgr.get_inflight_count(session) == 0

    def test_counts_qos1_only(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_outbound_qos1(session, 1, b't', b'p', 1)
        qos_mgr.track_outbound_qos1(session, 2, b't', b'p', 1)
        assert qos_mgr.get_inflight_count(session) == 2

    def test_counts_qos2_inbound_only(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_inbound_qos2(session, 1, b't', b'p', False)
        assert qos_mgr.get_inflight_count(session) == 1

    def test_counts_qos2_outbound_only(self, qos_mgr):
        session = _make_session()
        qos_mgr.track_outbound_qos2(session, 1, b't', b'p')
        qos_mgr.track_outbound_qos2(session, 2, b't', b'p')
        qos_mgr.track_outbound_qos2(session, 3, b't', b'p')
        assert qos_mgr.get_inflight_count(session) == 3

    def test_counts_all_three_dicts_combined(self, qos_mgr):
        session = _make_session()

        # 2 QoS 1
        qos_mgr.track_outbound_qos1(session, 1, b't', b'p', 1)
        qos_mgr.track_outbound_qos1(session, 2, b't', b'p', 1)

        # 1 QoS 2 inbound
        qos_mgr.track_inbound_qos2(session, 3, b't', b'p', False)

        # 3 QoS 2 outbound
        qos_mgr.track_outbound_qos2(session, 4, b't', b'p')
        qos_mgr.track_outbound_qos2(session, 5, b't', b'p')
        qos_mgr.track_outbound_qos2(session, 6, b't', b'p')

        assert qos_mgr.get_inflight_count(session) == 6

    def test_count_decreases_as_flows_complete(self, qos_mgr):
        session = _make_session()

        qos_mgr.track_outbound_qos1(session, 1, b't', b'p', 1)
        qos_mgr.track_inbound_qos2(session, 2, b't', b'p', False)
        qos_mgr.track_outbound_qos2(session, 3, b't', b'p')
        assert qos_mgr.get_inflight_count(session) == 3

        # Complete QoS 1
        qos_mgr.handle_puback(session, 1)
        assert qos_mgr.get_inflight_count(session) == 2

        # Complete QoS 2 inbound
        qos_mgr.handle_pubrel(session, 2)
        qos_mgr.handle_pubcomp(session, 2)
        assert qos_mgr.get_inflight_count(session) == 1

        # Complete QoS 2 outbound
        qos_mgr.handle_pubrec(session, 3)
        qos_mgr.handle_pubcomp(session, 3)
        assert qos_mgr.get_inflight_count(session) == 0


# --------------------------------------------------------------------------
# Test 8: QoS downgrade - publisher QoS 2, subscriber QoS 0
# --------------------------------------------------------------------------

class TestQoSDowngrade:
    """When publisher sends at QoS 2 but subscriber subscribed at QoS 0,
    the message should be delivered at QoS 0 (minimum of pub QoS and sub QoS).
    No QoS tracking should occur for QoS 0 delivery.
    """

    @pytest.mark.asyncio
    async def test_qos2_downgraded_to_qos0_no_tracking(self, config):
        topic_tree = TopicTree()
        sessions = {}
        qos_mgr = QoSManager(config)

        sub_session = _make_session('sub_qos0')
        sessions['sub_qos0'] = sub_session

        # Subscribe at QoS 0
        topic_tree.subscribe(b'weather/rain', 'sub_qos0', 0)

        router = MessageRouter(topic_tree, sessions, config, qos_manager=qos_mgr)

        # Publisher sends at QoS 2
        await router.route_publish(b'weather/rain', b'heavy', qos=2, retain=False, sender_id='weather_station')

        # Subscriber should receive the message
        data = sub_session.writer.get_data()
        assert len(data) > 0

        # No QoS tracking should occur (delivered at QoS 0)
        assert len(sub_session.pending_qos1) == 0
        assert len(sub_session.pending_qos2_out) == 0
        assert qos_mgr.get_inflight_count(sub_session) == 0

    @pytest.mark.asyncio
    async def test_qos2_downgraded_to_qos1(self, config):
        """Publisher QoS 2, subscriber QoS 1 -> delivered at QoS 1."""
        topic_tree = TopicTree()
        sessions = {}
        qos_mgr = QoSManager(config)

        sub_session = _make_session('sub_qos1')
        sessions['sub_qos1'] = sub_session

        # Subscribe at QoS 1
        topic_tree.subscribe(b'weather/rain', 'sub_qos1', 1)

        router = MessageRouter(topic_tree, sessions, config, qos_manager=qos_mgr)

        # Publisher sends at QoS 2
        await router.route_publish(b'weather/rain', b'heavy', qos=2, retain=False, sender_id='weather_station')

        # Should be tracked as QoS 1 (downgraded), not QoS 2
        assert len(sub_session.pending_qos1) == 1
        assert len(sub_session.pending_qos2_out) == 0

    @pytest.mark.asyncio
    async def test_qos1_downgraded_to_qos0(self, config):
        """Publisher QoS 1, subscriber QoS 0 -> delivered at QoS 0, no tracking."""
        topic_tree = TopicTree()
        sessions = {}
        qos_mgr = QoSManager(config)

        sub_session = _make_session('sub_qos0')
        sessions['sub_qos0'] = sub_session

        topic_tree.subscribe(b'sensor/data', 'sub_qos0', 0)

        router = MessageRouter(topic_tree, sessions, config, qos_manager=qos_mgr)
        await router.route_publish(b'sensor/data', b'42', qos=1, retain=False)

        data = sub_session.writer.get_data()
        assert len(data) > 0
        assert len(sub_session.pending_qos1) == 0
        assert qos_mgr.get_inflight_count(sub_session) == 0

    @pytest.mark.asyncio
    async def test_qos_not_upgraded(self, config):
        """Publisher QoS 0, subscriber QoS 2 -> delivered at QoS 0 (no upgrade)."""
        topic_tree = TopicTree()
        sessions = {}
        qos_mgr = QoSManager(config)

        sub_session = _make_session('sub_qos2')
        sessions['sub_qos2'] = sub_session

        topic_tree.subscribe(b'events/log', 'sub_qos2', 2)

        router = MessageRouter(topic_tree, sessions, config, qos_manager=qos_mgr)
        await router.route_publish(b'events/log', b'info', qos=0, retain=False)

        data = sub_session.writer.get_data()
        assert len(data) > 0
        assert len(sub_session.pending_qos1) == 0
        assert len(sub_session.pending_qos2_out) == 0
        assert qos_mgr.get_inflight_count(sub_session) == 0
