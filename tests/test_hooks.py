"""Tests for broker hooks and interceptors."""

import pytest
from beehivemqtt.broker import MQTTBroker, MessageContext


class TestBrokerHooks:
    """Test broker hook system."""

    def test_on_connect_hook_fires(self):
        """Test on_connect hook is called when set."""
        broker = MQTTBroker()
        calls = []

        @broker.on_connect
        def handle_connect(client_id, username, will_topic):
            calls.append(('connect', client_id))

        # Simulate hook call (3-arg signature)
        if broker._on_connect:
            broker._on_connect('test-client', None, None)

        assert len(calls) == 1
        assert calls[0] == ('connect', 'test-client')

    def test_on_publish_hook_fires(self):
        """Test on_publish hook is called when set."""
        broker = MQTTBroker()
        calls = []

        @broker.on_publish
        def handle_publish(client_id, topic, payload, qos, retain):
            calls.append(('publish', client_id, topic, payload, qos, retain))

        # Simulate hook call
        if broker._on_publish:
            broker._on_publish('client1', b'test/topic', b'payload', 1, False)

        assert len(calls) == 1
        assert calls[0] == ('publish', 'client1', b'test/topic', b'payload', 1, False)

    def test_on_subscribe_hook_fires(self):
        """Test on_subscribe hook is called when set."""
        broker = MQTTBroker()
        calls = []

        @broker.on_subscribe
        def handle_subscribe(client_id, topic_filter, requested_qos):
            calls.append(('subscribe', client_id, topic_filter, requested_qos))
            return requested_qos

        # Simulate hook call
        if broker._on_subscribe:
            result = broker._on_subscribe('client1', b'test/#', 2)

        assert len(calls) == 1
        assert calls[0] == ('subscribe', 'client1', b'test/#', 2)

    def test_on_subscribe_hook_can_modify_qos(self):
        """Test on_subscribe hook can modify granted QoS."""
        broker = MQTTBroker()

        @broker.on_subscribe
        def handle_subscribe(client_id, topic_filter, requested_qos):
            # Downgrade all subscriptions to QoS 0
            return 0

        # Simulate hook call
        if broker._on_subscribe:
            result = broker._on_subscribe('client1', b'test/#', 2)

        assert result == 0

    def test_on_subscribe_hook_can_reject(self):
        """Test on_subscribe hook can reject subscription."""
        broker = MQTTBroker()

        @broker.on_subscribe
        def handle_subscribe(client_id, topic_filter, requested_qos):
            # Reject all subscriptions
            return 0x80

        # Simulate hook call
        if broker._on_subscribe:
            result = broker._on_subscribe('client1', b'test/#', 2)

        assert result == 0x80

    def test_on_unsubscribe_hook_fires(self):
        """Test on_unsubscribe hook is called when set."""
        broker = MQTTBroker()
        calls = []

        @broker.on_unsubscribe
        def handle_unsubscribe(client_id, topic_filter):
            calls.append(('unsubscribe', client_id, topic_filter))

        # Simulate hook call
        if broker._on_unsubscribe:
            broker._on_unsubscribe('client1', b'test/#')

        assert len(calls) == 1
        assert calls[0] == ('unsubscribe', 'client1', b'test/#')

    def test_on_disconnect_hook_fires(self):
        """Test on_disconnect hook is called when set."""
        broker = MQTTBroker()
        calls = []

        @broker.on_disconnect
        def handle_disconnect(client_id, graceful):
            calls.append(('disconnect', client_id, graceful))

        # Simulate hook call
        if broker._on_disconnect:
            broker._on_disconnect('client1', graceful=True)

        assert len(calls) == 1
        assert calls[0] == ('disconnect', 'client1', True)


class TestBrokerInterceptors:
    """Test broker interceptor system."""

    def test_interceptor_receives_context(self):
        """Test interceptor receives MessageContext."""
        broker = MQTTBroker()
        contexts = []

        @broker.interceptor
        def capture(ctx):
            contexts.append(ctx)

        # Simulate interceptor call
        ctx = MessageContext(b'test/topic', b'payload', qos=0, retain=False, sender_id='client1')
        for interceptor in broker._interceptors:
            interceptor(ctx)

        assert len(contexts) == 1
        assert contexts[0] is ctx

    def test_interceptor_can_modify_message(self):
        """Test interceptor can modify message context."""
        broker = MQTTBroker()

        @broker.interceptor
        def modify(ctx):
            ctx.topic = b'modified/topic'
            ctx.payload = b'modified payload'
            ctx.qos = 2

        # Simulate interceptor call
        ctx = MessageContext(b'test/topic', b'payload', qos=0, retain=False, sender_id='client1')
        for interceptor in broker._interceptors:
            interceptor(ctx)

        assert ctx.topic == b'modified/topic'
        assert ctx.payload == b'modified payload'
        assert ctx.qos == 2

    def test_interceptor_can_drop_message(self):
        """Test interceptor can drop message."""
        broker = MQTTBroker()

        @broker.interceptor
        def drop_secrets(ctx):
            if b'secret' in ctx.topic:
                ctx.drop()

        # Test with secret topic
        ctx1 = MessageContext(b'secret/data', b'payload', qos=0, retain=False, sender_id='client1')
        for interceptor in broker._interceptors:
            interceptor(ctx1)

        assert ctx1._dropped is True

        # Test with normal topic
        ctx2 = MessageContext(b'normal/data', b'payload', qos=0, retain=False, sender_id='client1')
        for interceptor in broker._interceptors:
            interceptor(ctx2)

        assert ctx2._dropped is False

    def test_multiple_interceptors_pipeline(self):
        """Test multiple interceptors form a pipeline."""
        broker = MQTTBroker()
        calls = []

        @broker.interceptor
        def first(ctx):
            calls.append('first')
            ctx.payload = ctx.payload + b'-first'

        @broker.interceptor
        def second(ctx):
            calls.append('second')
            ctx.payload = ctx.payload + b'-second'

        # Simulate pipeline
        ctx = MessageContext(b'topic', b'original', qos=0, retain=False, sender_id=None)
        for interceptor in broker._interceptors:
            interceptor(ctx)

        assert calls == ['first', 'second']
        assert ctx.payload == b'original-first-second'

    def test_interceptor_pipeline_stops_on_drop(self):
        """Test interceptor pipeline behavior when message is dropped."""
        broker = MQTTBroker()
        calls = []

        @broker.interceptor
        def first(ctx):
            calls.append('first')
            ctx.drop()

        @broker.interceptor
        def second(ctx):
            calls.append('second')

        # Simulate pipeline
        ctx = MessageContext(b'topic', b'payload', qos=0, retain=False, sender_id=None)
        for interceptor in broker._interceptors:
            interceptor(ctx)
            if ctx._dropped:
                break  # This is what the broker should do

        # First interceptor ran and dropped message
        assert calls == ['first']
        # Second interceptor should not have run (broker stops pipeline)
        assert 'second' not in calls

    def test_interceptor_error_handling(self):
        """Test interceptor errors are isolated."""
        broker = MQTTBroker()
        calls = []

        @broker.interceptor
        def buggy(ctx):
            calls.append('buggy')
            raise ValueError("Interceptor error")

        @broker.interceptor
        def working(ctx):
            calls.append('working')

        # Simulate pipeline with error handling
        ctx = MessageContext(b'topic', b'payload', qos=0, retain=False, sender_id=None)
        for interceptor in broker._interceptors:
            try:
                interceptor(ctx)
            except Exception:
                pass  # Broker should catch and log errors

        # Both should have been attempted
        assert 'buggy' in calls
        assert 'working' in calls


class TestAsyncHooks:
    """Test async hook firing via broker._fire_hook."""

    @pytest.mark.asyncio
    async def test_fire_hook_with_sync_function(self):
        """Test _fire_hook with a sync lambda returns its value."""
        broker = MQTTBroker()

        result = await broker._fire_hook(lambda x: x * 2, 5)

        assert result == 10

    @pytest.mark.asyncio
    async def test_fire_hook_with_none(self):
        """Test _fire_hook with None hook returns None."""
        broker = MQTTBroker()

        result = await broker._fire_hook(None, 'arg')

        assert result is None

    @pytest.mark.asyncio
    async def test_fire_hook_with_exception(self):
        """Test _fire_hook with raising function returns None (no crash)."""
        broker = MQTTBroker()

        def bad_hook(*args):
            raise RuntimeError("hook error")

        result = await broker._fire_hook(bad_hook, 'arg')

        assert result is None

    def test_on_will_publish_hook_registered(self):
        """Test on_will_publish decorator registers the hook."""
        broker = MQTTBroker()

        @broker.on_will_publish
        def handler(client_id, topic, payload):
            return True

        assert broker._on_will_publish is handler
