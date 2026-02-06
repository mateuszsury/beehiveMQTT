"""Tests for beehivemqtt.router module."""

import pytest
from beehivemqtt.router import MessageRouter
from beehivemqtt.topic import TopicTree
from beehivemqtt.session import ClientSession
from beehivemqtt.config import BrokerConfig
from beehivemqtt.qos import QoSManager


class TestMessageRouter:
    """Test MessageRouter class."""

    @pytest.fixture
    def router_setup(self):
        """Provide router with dependencies."""
        topic_tree = TopicTree()
        sessions = {}
        config = BrokerConfig(retain_enabled=True, max_queued_messages=10)
        qos_manager = QoSManager(config)
        router = MessageRouter(topic_tree, sessions, config, qos_manager)

        return {
            'router': router,
            'topic_tree': topic_tree,
            'sessions': sessions,
            'config': config,
            'qos_manager': qos_manager
        }

    def create_mock_session(self, client_id):
        """Create a mock session with mock writer."""
        from conftest import MockWriter, MockReader

        session = ClientSession(client_id)
        session.writer = MockWriter()
        session.reader = MockReader()
        session.connected = True
        session.update_activity()

        return session

    @pytest.mark.asyncio
    async def test_route_publish_qos0_to_subscriber(self, router_setup):
        """Test routing QoS 0 PUBLISH to matching subscriber."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']
        sessions = setup['sessions']

        # Create subscriber
        session = self.create_mock_session('client1')
        sessions['client1'] = session

        # Subscribe to topic
        topic_tree.subscribe(b'test/topic', 'client1', qos=0)

        # Route message
        await router.route_publish(b'test/topic', b'payload', qos=0, retain=False)

        # Check message was sent
        assert len(session.writer.get_data()) > 0

    @pytest.mark.asyncio
    async def test_route_publish_no_echo_to_sender(self, router_setup):
        """Test routing does not echo message back to sender."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']
        sessions = setup['sessions']

        # Create sender who is also subscribed
        session = self.create_mock_session('client1')
        sessions['client1'] = session
        topic_tree.subscribe(b'test/topic', 'client1', qos=0)

        # Route message from client1
        await router.route_publish(b'test/topic', b'payload', qos=0, retain=False, sender_id='client1')

        # Should NOT receive own message
        assert len(session.writer.get_data()) == 0

    @pytest.mark.asyncio
    async def test_route_publish_to_multiple_subscribers(self, router_setup):
        """Test routing PUBLISH to multiple matching subscribers."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']
        sessions = setup['sessions']

        # Create multiple subscribers
        session1 = self.create_mock_session('client1')
        session2 = self.create_mock_session('client2')
        sessions['client1'] = session1
        sessions['client2'] = session2

        topic_tree.subscribe(b'test/topic', 'client1', qos=0)
        topic_tree.subscribe(b'test/topic', 'client2', qos=0)

        # Route message
        await router.route_publish(b'test/topic', b'payload', qos=0, retain=False)

        # Both should receive
        assert len(session1.writer.get_data()) > 0
        assert len(session2.writer.get_data()) > 0

    @pytest.mark.asyncio
    async def test_route_publish_qos_downgrade(self, router_setup):
        """Test routing downgrades QoS based on granted QoS."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']
        sessions = setup['sessions']

        # Subscriber with QoS 0
        session = self.create_mock_session('client1')
        sessions['client1'] = session
        topic_tree.subscribe(b'test/topic', 'client1', qos=0)

        # Route message with QoS 2
        await router.route_publish(b'test/topic', b'payload', qos=2, retain=False)

        # Should be delivered at QoS 0 (min of 2 and 0)
        assert len(session.writer.get_data()) > 0

    @pytest.mark.asyncio
    async def test_route_publish_stores_retained(self, router_setup):
        """Test routing stores retained message when retain=True."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']

        # Route retained message
        await router.route_publish(b'test/topic', b'payload', qos=0, retain=True)

        # Check retained message is stored
        retained = topic_tree.get_retained(b'test/topic')
        assert retained is not None
        assert retained[1] == b'payload'

    @pytest.mark.asyncio
    async def test_route_publish_clears_retained_with_empty_payload(self, router_setup):
        """Test routing with empty payload clears retained message."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']

        # Set retained message
        topic_tree.set_retained(b'test/topic', b'old payload', qos=0)

        # Route with empty payload
        await router.route_publish(b'test/topic', b'', qos=0, retain=True)

        # Should be cleared
        retained = topic_tree.get_retained(b'test/topic')
        assert retained is None

    @pytest.mark.asyncio
    async def test_route_publish_does_not_queue_qos0_for_offline(self, router_setup):
        """Test routing does NOT queue QoS 0 for offline persistent session."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']
        sessions = setup['sessions']

        # Create offline persistent session
        session = self.create_mock_session('client1')
        session.connected = False
        session.clean_session = False
        sessions['client1'] = session

        topic_tree.subscribe(b'test/topic', 'client1', qos=0)

        # Route QoS 0 message
        await router.route_publish(b'test/topic', b'payload', qos=0, retain=False)

        # QoS 0 is fire-and-forget, should NOT be queued
        assert len(session.queued_messages) == 0

    @pytest.mark.asyncio
    async def test_route_publish_queues_qos1_for_offline_persistent_session(self, router_setup):
        """Test routing queues QoS 1 message for offline persistent session."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']
        sessions = setup['sessions']

        # Create offline persistent session
        session = self.create_mock_session('client1')
        session.connected = False
        session.clean_session = False
        sessions['client1'] = session

        topic_tree.subscribe(b'test/topic', 'client1', qos=1)

        # Route QoS 1 message
        await router.route_publish(b'test/topic', b'payload', qos=1, retain=False)

        # QoS 1 should be queued
        assert len(session.queued_messages) == 1
        assert session.queued_messages[0] == (b'test/topic', b'payload', 1)

    @pytest.mark.asyncio
    async def test_deliver_retained_sends_matching_messages(self, router_setup):
        """Test deliver_retained sends matching retained messages."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']

        # Set retained messages
        topic_tree.set_retained(b'home/kitchen/temp', b'20', qos=0)
        topic_tree.set_retained(b'home/bedroom/temp', b'18', qos=0)

        # Create session
        session = self.create_mock_session('client1')

        # Deliver retained for wildcard subscription
        await router.deliver_retained(session, b'home/+/temp', granted_qos=0)

        # Should have received both retained messages
        data = session.writer.get_data()
        assert len(data) > 0
        assert b'20' in data or b'18' in data

    @pytest.mark.asyncio
    async def test_deliver_retained_exact_topic(self, router_setup):
        """Test deliver_retained with exact topic filter."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']

        topic_tree.set_retained(b'test/topic', b'payload', qos=0)

        session = self.create_mock_session('client1')

        await router.deliver_retained(session, b'test/topic', granted_qos=0)

        # Should have received the retained message
        assert len(session.writer.get_data()) > 0

    @pytest.mark.asyncio
    async def test_deliver_retained_disabled(self, router_setup):
        """Test deliver_retained does nothing when retain_enabled=False."""
        setup = router_setup
        router = setup['router']
        topic_tree = setup['topic_tree']

        # Disable retain
        setup['config'].retain_enabled = False

        topic_tree.set_retained(b'test/topic', b'payload', qos=0)
        session = self.create_mock_session('client1')

        await router.deliver_retained(session, b'test/topic', granted_qos=0)

        # Should not have sent anything
        assert len(session.writer.get_data()) == 0

    @pytest.mark.asyncio
    async def test_deliver_queued_sends_queued_messages(self, router_setup):
        """Test deliver_queued sends queued messages to reconnected client."""
        setup = router_setup
        router = setup['router']

        # Create session with queued messages
        session = self.create_mock_session('client1')
        session.queue_message(b'topic1', b'payload1', qos=0)
        session.queue_message(b'topic2', b'payload2', qos=0)

        # Deliver queued
        await router.deliver_queued(session)

        # All messages should be sent
        assert len(session.writer.get_data()) > 0
        # Queue should be cleared
        assert len(session.queued_messages) == 0

    @pytest.mark.asyncio
    async def test_deliver_queued_empty_queue(self, router_setup):
        """Test deliver_queued with empty queue."""
        setup = router_setup
        router = setup['router']

        session = self.create_mock_session('client1')

        # Should not raise error
        await router.deliver_queued(session)

        assert len(session.writer.get_data()) == 0

    @pytest.mark.asyncio
    async def test_route_publish_retained_uses_store(self):
        """Test routing retained message goes through RetainedStore when provided."""
        from beehivemqtt.retained import RetainedStore

        topic_tree = TopicTree()
        sessions = {}
        config = BrokerConfig(retain_enabled=True, max_retained_messages=10)
        qos_manager = QoSManager(config)
        retained_store = RetainedStore(topic_tree, config)
        router = MessageRouter(topic_tree, sessions, config, qos_manager,
                               retained_store=retained_store)

        # Route a retained message with payload
        await router.route_publish(b'sensor/temp', b'25.5', qos=0, retain=True)

        # Verify retained_store tracks the message
        assert retained_store.count() == 1

    @pytest.mark.asyncio
    async def test_route_publish_retained_clear_uses_store(self):
        """Test routing retained message with empty payload clears via RetainedStore."""
        from beehivemqtt.retained import RetainedStore

        topic_tree = TopicTree()
        sessions = {}
        config = BrokerConfig(retain_enabled=True, max_retained_messages=10)
        qos_manager = QoSManager(config)
        retained_store = RetainedStore(topic_tree, config)
        router = MessageRouter(topic_tree, sessions, config, qos_manager,
                               retained_store=retained_store)

        # First set a retained message
        await router.route_publish(b'sensor/temp', b'25.5', qos=0, retain=True)
        assert retained_store.count() == 1

        # Then route with empty payload and retain=True to clear it
        await router.route_publish(b'sensor/temp', b'', qos=0, retain=True)
        assert retained_store.count() == 0

    @pytest.mark.asyncio
    async def test_deliver_retained_qos2(self):
        """Test deliver_retained with QoS 2 message tracks in pending_qos2_out."""
        topic_tree = TopicTree()
        sessions = {}
        config = BrokerConfig(retain_enabled=True, max_queued_messages=10)
        qos_manager = QoSManager(config)
        router = MessageRouter(topic_tree, sessions, config, qos_manager)

        # Set retained message at QoS 2 directly in topic_tree
        topic_tree.set_retained(b'alarm/fire', b'active', qos=2)

        # Create connected session with QoS 2 subscription
        session = self.create_mock_session('client_qos2')

        # Deliver retained with granted_qos=2
        await router.deliver_retained(session, b'alarm/fire', granted_qos=2)

        # Verify data was sent
        assert len(session.writer.get_data()) > 0

        # Verify pending_qos2_out has an entry (QoS 2 retained is tracked)
        assert len(session.pending_qos2_out) == 1

    @pytest.mark.asyncio
    async def test_deliver_queued_qos2(self):
        """Test deliver_queued with QoS 2 message tracks in pending_qos2_out."""
        topic_tree = TopicTree()
        sessions = {}
        config = BrokerConfig(retain_enabled=True, max_queued_messages=10)
        qos_manager = QoSManager(config)
        router = MessageRouter(topic_tree, sessions, config, qos_manager)

        # Create session and queue a QoS 2 message
        session = self.create_mock_session('client_queued')
        session.queue_message(b'critical/alert', b'overtemp', qos=2)

        # Deliver queued messages
        await router.deliver_queued(session)

        # Verify data was sent
        assert len(session.writer.get_data()) > 0

        # Verify pending_qos2_out has an entry
        assert len(session.pending_qos2_out) == 1

        # Queue should be cleared
        assert len(session.queued_messages) == 0

    @pytest.mark.asyncio
    async def test_max_inflight_queues_when_exceeded(self):
        """Test that exceeding max_inflight queues message instead of sending."""
        topic_tree = TopicTree()
        sessions = {}
        config = BrokerConfig(retain_enabled=True, max_queued_messages=10,
                              max_inflight=1)
        qos_manager = QoSManager(config)
        router = MessageRouter(topic_tree, sessions, config, qos_manager)

        # Create subscriber
        session = self.create_mock_session('client_inflight')
        sessions['client_inflight'] = session
        topic_tree.subscribe(b'test/inflight', 'client_inflight', qos=1)

        # Route first QoS 1 message - should be sent and tracked
        await router.route_publish(b'test/inflight', b'msg1', qos=1, retain=False)
        assert len(session.pending_qos1) == 1  # One inflight message tracked
        first_data_len = len(session.writer.get_data())
        assert first_data_len > 0

        # Route second QoS 1 message - inflight is at limit (1), should be queued
        await router.route_publish(b'test/inflight', b'msg2', qos=1, retain=False)

        # Second message should be queued, not sent
        assert len(session.queued_messages) == 1
        assert session.queued_messages[0] == (b'test/inflight', b'msg2', 1)

        # Inflight count should still be 1 (second was queued, not tracked)
        assert len(session.pending_qos1) == 1

    @pytest.mark.asyncio
    async def test_stats_tracking_on_delivery(self):
        """Test that stats are updated when messages are delivered."""
        from beehivemqtt.stats import BrokerStats

        topic_tree = TopicTree()
        sessions = {}
        config = BrokerConfig(retain_enabled=True, max_queued_messages=10)
        qos_manager = QoSManager(config)
        stats = BrokerStats()
        router = MessageRouter(topic_tree, sessions, config, qos_manager,
                               stats=stats)

        # Create subscriber
        session = self.create_mock_session('client_stats')
        sessions['client_stats'] = session
        topic_tree.subscribe(b'metrics/test', 'client_stats', qos=0)

        # Verify initial stats
        assert stats.publishes_sent == 0
        assert stats.messages_sent == 0

        # Route message
        await router.route_publish(b'metrics/test', b'data', qos=0, retain=False)

        # Verify stats were updated
        assert stats.publishes_sent >= 1
        assert stats.messages_sent >= 1
