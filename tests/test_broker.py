"""Tests for beehivemqtt.broker module (basic initialization and methods)."""

import pytest
from beehivemqtt.broker import MQTTBroker, MessageContext
from beehivemqtt.config import BrokerConfig


class TestMessageContext:
    """Test MessageContext class."""

    def test_initialization(self):
        """Test MessageContext initialization."""
        ctx = MessageContext(b'test/topic', b'payload', qos=1, retain=True, sender_id='client1')

        assert ctx.topic == b'test/topic'
        assert ctx.payload == b'payload'
        assert ctx.qos == 1
        assert ctx.retain is True
        assert ctx.sender_id == 'client1'
        assert ctx._dropped is False

    def test_drop_marks_as_dropped(self):
        """Test drop() marks context as dropped."""
        ctx = MessageContext(b'topic', b'data', qos=0, retain=False, sender_id=None)

        ctx.drop()

        assert ctx._dropped is True


class TestMQTTBroker:
    """Test MQTTBroker class."""

    def test_initialization_defaults(self):
        """Test MQTTBroker initialization with defaults."""
        broker = MQTTBroker()

        assert broker.config is not None
        assert broker.sessions == {}
        assert broker.topic_tree is not None
        assert broker.qos_manager is not None
        assert broker.retained_store is not None
        assert broker.router is not None
        assert broker.session_manager is not None
        assert broker.stats is not None
        assert broker.auth is None
        assert broker._server is None
        assert broker._running is False

    def test_initialization_with_config(self):
        """Test MQTTBroker initialization with custom config."""
        config = BrokerConfig(port=8883, max_clients=5)
        broker = MQTTBroker(config=config)

        assert broker.config.port == 8883
        assert broker.config.max_clients == 5

    def test_initialization_with_auth(self):
        """Test MQTTBroker initialization with auth provider."""
        from beehivemqtt.auth import AuthProvider
        auth = AuthProvider()
        broker = MQTTBroker(auth=auth)

        assert broker.auth is auth

    def test_on_connect_decorator(self):
        """Test on_connect decorator registers hook."""
        broker = MQTTBroker()

        @broker.on_connect
        def handler(client_id):
            pass

        assert broker._on_connect is handler

    def test_on_publish_decorator(self):
        """Test on_publish decorator registers hook."""
        broker = MQTTBroker()

        @broker.on_publish
        def handler(client_id, topic, payload, qos, retain):
            pass

        assert broker._on_publish is handler

    def test_on_subscribe_decorator(self):
        """Test on_subscribe decorator registers hook."""
        broker = MQTTBroker()

        @broker.on_subscribe
        def handler(client_id, topic_filter, requested_qos):
            return requested_qos

        assert broker._on_subscribe is handler

    def test_on_unsubscribe_decorator(self):
        """Test on_unsubscribe decorator registers hook."""
        broker = MQTTBroker()

        @broker.on_unsubscribe
        def handler(client_id, topic_filter):
            pass

        assert broker._on_unsubscribe is handler

    def test_on_disconnect_decorator(self):
        """Test on_disconnect decorator registers hook."""
        broker = MQTTBroker()

        @broker.on_disconnect
        def handler(client_id, graceful):
            pass

        assert broker._on_disconnect is handler

    def test_interceptor_decorator(self):
        """Test interceptor decorator registers interceptor."""
        broker = MQTTBroker()

        @broker.interceptor
        def my_filter(ctx):
            pass

        assert len(broker._interceptors) == 1
        assert broker._interceptors[0] is my_filter

    def test_multiple_interceptors(self):
        """Test registering multiple interceptors."""
        broker = MQTTBroker()

        @broker.interceptor
        def filter1(ctx):
            pass

        @broker.interceptor
        def filter2(ctx):
            pass

        assert len(broker._interceptors) == 2
        assert broker._interceptors[0] is filter1
        assert broker._interceptors[1] is filter2

    def test_get_stats_returns_dict(self):
        """Test get_stats returns expected dictionary."""
        broker = MQTTBroker()

        stats = broker.get_stats()

        assert isinstance(stats, dict)
        assert 'uptime' in stats
        assert 'clients_connected' in stats
        assert 'clients_total' in stats
        assert 'messages_received' in stats
        assert 'messages_sent' in stats
        assert 'publishes_received' in stats
        assert 'publishes_sent' in stats
        assert 'bytes_received' in stats
        assert 'bytes_sent' in stats
        assert 'connections_total' in stats
        assert 'subscriptions' in stats
        assert 'retained_messages' in stats

    def test_get_clients_empty(self):
        """Test get_clients on empty broker."""
        broker = MQTTBroker()

        clients = broker.get_clients()

        assert clients == []

    def test_get_subscriptions_empty(self):
        """Test get_subscriptions on empty broker."""
        broker = MQTTBroker()

        subscriptions = broker.get_subscriptions()

        assert subscriptions == {}

    def test_get_retained_messages_empty(self):
        """Test get_retained_messages on empty broker."""
        broker = MQTTBroker()

        messages = broker.get_retained_messages()

        assert messages == []

    @pytest.mark.asyncio
    async def test_publish_method_converts_strings(self):
        """Test publish method converts string topic/payload to bytes."""
        broker = MQTTBroker()

        # This should not raise an error
        await broker.publish('test/topic', 'hello', qos=0, retain=False)

        # Check stats were updated
        assert broker.stats.publishes_sent == 1

    @pytest.mark.asyncio
    async def test_publish_method_accepts_bytes(self):
        """Test publish method accepts bytes topic/payload."""
        broker = MQTTBroker()

        await broker.publish(b'test/topic', b'hello', qos=1, retain=True)

        assert broker.stats.publishes_sent == 1

    def test_clear_retained_specific_topic(self):
        """Test clearing retained message for specific topic."""
        broker = MQTTBroker()

        # Set retained message directly on store
        broker.retained_store.set(b'test/topic', b'data', qos=0)

        # Clear it
        broker.clear_retained(b'test/topic')

        assert broker.retained_store.count() == 0

    def test_clear_retained_all(self):
        """Test clearing all retained messages."""
        broker = MQTTBroker()

        # Set multiple retained messages
        broker.retained_store.set(b'topic1', b'data1', qos=0)
        broker.retained_store.set(b'topic2', b'data2', qos=0)

        # Clear all
        broker.clear_retained()

        assert broker.retained_store.count() == 0

    @pytest.mark.asyncio
    async def test_disconnect_client_nonexistent(self):
        """Test disconnecting non-existent client returns False."""
        broker = MQTTBroker()

        result = await broker.disconnect_client('nonexistent')

        assert result is False

    def test_on_will_publish_decorator(self):
        """Test on_will_publish decorator registers hook."""
        broker = MQTTBroker()

        @broker.on_will_publish
        def handler(client_id, topic, payload):
            return True

        assert broker._on_will_publish is handler

    def test_router_has_retained_store(self):
        """Test broker.router.retained_store is broker.retained_store."""
        broker = MQTTBroker()

        assert broker.router.retained_store is broker.retained_store

    def test_router_has_stats(self):
        """Test broker.router.stats is broker.stats."""
        broker = MQTTBroker()

        assert broker.router.stats is broker.stats

    def test_config_has_no_keepalive_timeout(self):
        """Test broker.config.no_keepalive_timeout default is 3600."""
        broker = MQTTBroker()

        assert broker.config.no_keepalive_timeout == 3600

    def test_config_has_max_topic_levels(self):
        """Test broker.config.max_topic_levels default is 8."""
        broker = MQTTBroker()

        assert broker.config.max_topic_levels == 8
