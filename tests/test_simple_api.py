"""Tests for beehivemqtt.simple module."""

import pytest
from beehivemqtt.simple import BeehiveBrokerSimple
from beehivemqtt.auth import DictAuthProvider


class TestBeehiveBrokerSimple:
    """Test BeehiveBrokerSimple class."""

    def test_initialization_defaults(self):
        """Test initialization with default parameters."""
        broker = BeehiveBrokerSimple()

        assert broker._broker is not None
        assert broker._broker.config.port == 1883
        assert broker._broker.config.max_clients == 10

    def test_initialization_with_port(self):
        """Test initialization with custom port."""
        broker = BeehiveBrokerSimple(port=8883)

        assert broker._broker.config.port == 8883

    def test_initialization_with_max_clients(self):
        """Test initialization with custom max_clients."""
        broker = BeehiveBrokerSimple(max_clients=20)

        assert broker._broker.config.max_clients == 20

    def test_initialization_with_users_creates_dict_auth(self):
        """Test initialization with users parameter creates DictAuthProvider."""
        users = {'user1': 'pass1', 'user2': 'pass2'}
        broker = BeehiveBrokerSimple(users=users)

        assert broker._broker.auth is not None
        assert isinstance(broker._broker.auth, DictAuthProvider)

    def test_initialization_with_custom_auth(self):
        """Test initialization with custom auth provider."""
        from beehivemqtt.auth import AuthProvider
        custom_auth = AuthProvider()

        broker = BeehiveBrokerSimple(auth=custom_auth)

        assert broker._broker.auth is custom_auth

    def test_initialization_with_log_level(self):
        """Test initialization with custom log level."""
        broker = BeehiveBrokerSimple(log_level='DEBUG')

        assert broker._broker.config.log_level == 'DEBUG'

    def test_on_message_callback_wired(self):
        """Test on_message callback is wired to broker."""
        messages = []

        def on_msg(topic, payload, client_id):
            messages.append((topic, payload, client_id))

        broker = BeehiveBrokerSimple(on_message=on_msg)

        # Check that on_publish hook is set
        assert broker._broker._on_publish is not None

        # Simulate calling the hook
        broker._broker._on_publish('client1', b'test/topic', b'payload', 0, False)

        assert len(messages) == 1
        assert messages[0] == (b'test/topic', b'payload', 'client1')

    def test_on_connect_callback_wired(self):
        """Test on_connect callback is wired to broker."""
        connections = []

        def on_conn(client_id):
            connections.append(client_id)

        broker = BeehiveBrokerSimple(on_connect=on_conn)

        assert broker._broker._on_connect is not None

        # Simulate calling the hook (3-arg signature: client_id, username, will_topic)
        broker._broker._on_connect('client1', None, None)

        assert len(connections) == 1
        assert connections[0] == 'client1'

    def test_on_disconnect_callback_wired(self):
        """Test on_disconnect callback is wired to broker."""
        disconnections = []

        def on_disc(client_id):
            disconnections.append(client_id)

        broker = BeehiveBrokerSimple(on_disconnect=on_disc)

        assert broker._broker._on_disconnect is not None

        # Simulate calling the hook
        broker._broker._on_disconnect('client1', graceful=True)

        assert len(disconnections) == 1
        assert disconnections[0] == 'client1'

    def test_all_callbacks_together(self):
        """Test initialization with all callbacks."""
        messages = []
        connections = []
        disconnections = []

        def on_msg(topic, payload, client_id):
            messages.append((topic, payload, client_id))

        def on_conn(client_id):
            connections.append(client_id)

        def on_disc(client_id):
            disconnections.append(client_id)

        broker = BeehiveBrokerSimple(
            on_message=on_msg,
            on_connect=on_conn,
            on_disconnect=on_disc
        )

        # All hooks should be wired
        assert broker._broker._on_publish is not None
        assert broker._broker._on_connect is not None
        assert broker._broker._on_disconnect is not None

    def test_subscribe_method(self):
        """Test subscribe() registers a filtered callback."""
        received = []

        def callback(topic, payload, client_id):
            received.append((topic, payload, client_id))

        broker = BeehiveBrokerSimple()
        broker.subscribe('sensor/+/temp', callback)

        # on_publish hook should be set now
        assert broker._broker._on_publish is not None

        # Simulate matching publish
        broker._broker._on_publish('c1', b'sensor/living/temp', b'22', 0, False)
        assert len(received) == 1
        assert received[0] == (b'sensor/living/temp', b'22', 'c1')

        # Simulate non-matching publish
        broker._broker._on_publish('c2', b'sensor/living/humidity', b'60', 0, False)
        assert len(received) == 1  # Should not have received anything new

    def test_subscribe_with_hash_wildcard(self):
        """Test subscribe with # wildcard matches deep topics."""
        received = []

        def callback(topic, payload, client_id):
            received.append(topic)

        broker = BeehiveBrokerSimple()
        broker.subscribe('home/#', callback)

        broker._broker._on_publish('c1', b'home/kitchen/temp', b'data', 0, False)
        broker._broker._on_publish('c1', b'home/bedroom', b'data', 0, False)
        broker._broker._on_publish('c1', b'office/desk', b'data', 0, False)

        assert len(received) == 2
        assert b'home/kitchen/temp' in received
        assert b'home/bedroom' in received

    def test_subscribe_chains_existing_hook(self):
        """Test subscribe chains with existing on_publish hook."""
        messages = []
        subscriptions = []

        def on_msg(topic, payload, client_id):
            messages.append(topic)

        def sub_callback(topic, payload, client_id):
            subscriptions.append(topic)

        broker = BeehiveBrokerSimple(on_message=on_msg)
        broker.subscribe('test/#', sub_callback)

        # Both hooks should fire
        broker._broker._on_publish('c1', b'test/topic', b'data', 0, False)
        assert len(messages) == 1
        assert len(subscriptions) == 1

    def test_subscribe_multiple_filters(self):
        """Test multiple subscribe calls with different filters."""
        temp_data = []
        humidity_data = []

        broker = BeehiveBrokerSimple()
        broker.subscribe('sensor/+/temp', lambda t, p, c: temp_data.append(t))
        broker.subscribe('sensor/+/humidity', lambda t, p, c: humidity_data.append(t))

        broker._broker._on_publish('c1', b'sensor/a/temp', b'22', 0, False)
        broker._broker._on_publish('c1', b'sensor/a/humidity', b'60', 0, False)

        assert len(temp_data) == 1
        assert len(humidity_data) == 1


class TestFilterMatchesTopic:
    """Test the _filter_matches_topic helper function."""

    def test_exact_match(self):
        """Test exact topic matching."""
        from beehivemqtt.simple import _filter_matches_topic
        assert _filter_matches_topic('home/temp', 'home/temp') is True
        assert _filter_matches_topic('home/temp', 'home/humidity') is False

    def test_plus_wildcard(self):
        """Test + wildcard matching."""
        from beehivemqtt.simple import _filter_matches_topic
        assert _filter_matches_topic('home/+/temp', 'home/kitchen/temp') is True
        assert _filter_matches_topic('home/+/temp', 'home/bedroom/temp') is True
        assert _filter_matches_topic('home/+/temp', 'home/kitchen/humidity') is False

    def test_hash_wildcard(self):
        """Test # wildcard matching."""
        from beehivemqtt.simple import _filter_matches_topic
        assert _filter_matches_topic('home/#', 'home/kitchen/temp') is True
        assert _filter_matches_topic('home/#', 'home') is True
        assert _filter_matches_topic('#', 'anything/at/all') is True

    def test_no_match_different_depth(self):
        """Test non-matching different topic depth."""
        from beehivemqtt.simple import _filter_matches_topic
        assert _filter_matches_topic('home/temp', 'home/temp/extra') is False
        assert _filter_matches_topic('home/a/b', 'home/a') is False


class TestRateLimiter:
    """Test RateLimiter interceptor."""

    def test_allows_under_limit(self):
        """Test messages under rate limit are allowed."""
        from beehivemqtt.ratelimit import RateLimiter
        from beehivemqtt.broker import MessageContext

        limiter = RateLimiter(max_rate=5, window_seconds=1)

        for _ in range(5):
            ctx = MessageContext(b'topic', b'payload', 0, False, 'client1')
            limiter(ctx)
            assert not ctx._dropped

    def test_drops_over_limit(self):
        """Test messages over rate limit are dropped."""
        from beehivemqtt.ratelimit import RateLimiter
        from beehivemqtt.broker import MessageContext

        limiter = RateLimiter(max_rate=3, window_seconds=10)

        for i in range(3):
            ctx = MessageContext(b'topic', b'payload', 0, False, 'client1')
            limiter(ctx)
            assert not ctx._dropped

        # 4th message should be dropped
        ctx = MessageContext(b'topic', b'payload', 0, False, 'client1')
        limiter(ctx)
        assert ctx._dropped

    def test_broker_publishes_not_limited(self):
        """Test broker-internal publishes (sender_id=None) are not limited."""
        from beehivemqtt.ratelimit import RateLimiter
        from beehivemqtt.broker import MessageContext

        limiter = RateLimiter(max_rate=1, window_seconds=10)

        for _ in range(5):
            ctx = MessageContext(b'topic', b'payload', 0, False, None)
            limiter(ctx)
            assert not ctx._dropped

    def test_per_client_buckets(self):
        """Test rate limiting is per-client."""
        from beehivemqtt.ratelimit import RateLimiter
        from beehivemqtt.broker import MessageContext

        limiter = RateLimiter(max_rate=2, window_seconds=10)

        # Client1 uses up their quota
        for _ in range(2):
            ctx = MessageContext(b'topic', b'payload', 0, False, 'client1')
            limiter(ctx)

        # Client2 should still be allowed
        ctx = MessageContext(b'topic', b'payload', 0, False, 'client2')
        limiter(ctx)
        assert not ctx._dropped

        # Client1 should be dropped
        ctx = MessageContext(b'topic', b'payload', 0, False, 'client1')
        limiter(ctx)
        assert ctx._dropped

    def test_cleanup_client(self):
        """Test cleanup_client removes bucket."""
        from beehivemqtt.ratelimit import RateLimiter
        from beehivemqtt.broker import MessageContext

        limiter = RateLimiter(max_rate=1, window_seconds=10)

        ctx = MessageContext(b'topic', b'payload', 0, False, 'client1')
        limiter(ctx)
        assert 'client1' in limiter._buckets

        limiter.cleanup_client('client1')
        assert 'client1' not in limiter._buckets

    def test_has_slots(self):
        """Test RateLimiter uses __slots__."""
        from beehivemqtt.ratelimit import RateLimiter
        assert hasattr(RateLimiter, '__slots__')
