"""Tests for beehivemqtt.retained module."""

import pytest
from beehivemqtt.retained import RetainedStore
from beehivemqtt.topic import TopicTree
from beehivemqtt.config import BrokerConfig


class TestRetainedStore:
    """Test RetainedStore class."""

    @pytest.fixture
    def retained_store(self):
        """Provide RetainedStore instance."""
        topic_tree = TopicTree()
        config = BrokerConfig(retain_enabled=True, max_retained_messages=10)
        return RetainedStore(topic_tree, config)

    def test_set_retained_message(self, retained_store):
        """Test setting a retained message."""
        result = retained_store.set(b'test/topic', b'payload', qos=1)

        assert result is True
        assert retained_store.count() == 1

    def test_set_retained_string_topic(self, retained_store):
        """Test setting retained message with string topic."""
        result = retained_store.set('string/topic', b'data', qos=0)

        assert result is True
        assert retained_store.count() == 1

    def test_set_retained_empty_payload_clears(self, retained_store):
        """Test setting retained with empty payload clears it."""
        retained_store.set(b'test/topic', b'payload', qos=1)
        assert retained_store.count() == 1

        result = retained_store.set(b'test/topic', b'', qos=0)

        assert result is True
        assert retained_store.count() == 0

    def test_set_retained_disabled(self):
        """Test setting retained when retain_enabled=False."""
        topic_tree = TopicTree()
        config = BrokerConfig(retain_enabled=False)
        store = RetainedStore(topic_tree, config)

        result = store.set(b'topic', b'payload', qos=0)

        assert result is False
        assert store.count() == 0

    def test_set_retained_at_limit_evicts_lru(self, retained_store):
        """Test LRU eviction when at max retained limit."""
        # Fill to limit
        for i in range(10):
            retained_store.set(('topic%d' % i).encode(), b'data', qos=0)

        # Add one more - should evict oldest (topic0) via LRU
        result = retained_store.set(b'topic10', b'data', qos=0)

        assert result is True
        assert retained_store.count() == 10
        # topic0 should have been evicted
        assert retained_store.topic_tree.get_retained('topic0') is None
        # topic10 should be present
        assert retained_store.topic_tree.get_retained('topic10') is not None

    def test_set_retained_replacing_existing_allowed_at_limit(self, retained_store):
        """Test replacing existing retained message is allowed even at limit."""
        # Fill to limit
        for i in range(10):
            retained_store.set(('topic%d' % i).encode(), b'data', qos=0)

        # Replace existing - should succeed
        result = retained_store.set(b'topic5', b'new data', qos=1)

        assert result is True
        assert retained_store.count() == 10

    def test_set_retained_clearing_allowed_at_limit(self, retained_store):
        """Test clearing retained message is always allowed."""
        # Fill to limit
        for i in range(10):
            retained_store.set(('topic%d' % i).encode(), b'data', qos=0)

        # Clear one - should succeed
        result = retained_store.set(b'topic5', b'', qos=0)

        assert result is True
        assert retained_store.count() == 9

    def test_get_matching_exact(self, retained_store):
        """Test getting retained messages matching exact topic."""
        retained_store.set(b'test/topic', b'payload', qos=1)

        messages = retained_store.get_matching(b'test/topic')

        assert len(messages) == 1
        assert messages[0] == (b'test/topic', b'payload', 1)

    def test_get_matching_with_wildcard(self, retained_store):
        """Test getting retained messages with wildcard filter."""
        retained_store.set(b'home/kitchen/temp', b'20', qos=0)
        retained_store.set(b'home/bedroom/temp', b'18', qos=0)

        messages = retained_store.get_matching(b'home/+/temp')

        assert len(messages) == 2

    def test_get_matching_disabled(self):
        """Test get_matching returns empty when retain_enabled=False."""
        topic_tree = TopicTree()
        config = BrokerConfig(retain_enabled=False)
        store = RetainedStore(topic_tree, config)

        messages = store.get_matching(b'#')

        assert messages == []

    def test_clear_specific_topic(self, retained_store):
        """Test clearing retained message for specific topic."""
        retained_store.set(b'topic1', b'data1', qos=0)
        retained_store.set(b'topic2', b'data2', qos=0)

        retained_store.clear(b'topic1')

        assert retained_store.count() == 1
        messages = retained_store.get_matching(b'#')
        assert len(messages) == 1
        assert messages[0][0] == b'topic2'

    def test_clear_all_topics(self, retained_store):
        """Test clearing all retained messages."""
        retained_store.set(b'topic1', b'data1', qos=0)
        retained_store.set(b'topic2', b'data2', qos=0)
        retained_store.set(b'topic3', b'data3', qos=0)

        retained_store.clear()

        assert retained_store.count() == 0

    def test_count_empty(self, retained_store):
        """Test count on empty store."""
        assert retained_store.count() == 0

    def test_count_multiple(self, retained_store):
        """Test count with multiple retained messages."""
        retained_store.set(b'topic1', b'data1', qos=0)
        retained_store.set(b'topic2', b'data2', qos=0)
        retained_store.set(b'topic3', b'data3', qos=0)

        assert retained_store.count() == 3
