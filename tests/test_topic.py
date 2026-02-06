"""Tests for beehivemqtt.topic module."""

import pytest
from beehivemqtt.topic import TopicTree, TopicNode


class TestTopicNode:
    """Test TopicNode structure."""

    def test_node_initialization(self):
        """Test TopicNode initializes with lazy children (None) and empty subscribers."""
        node = TopicNode()
        assert node.children is None  # Lazy initialization
        assert node.subscribers == {}
        assert node.retained is None


class TestTopicTreeSubscription:
    """Test topic tree subscription management."""

    def test_subscribe_simple_topic(self, topic_tree):
        """Test subscribing to a simple topic."""
        topic_tree.subscribe('home/temperature', 'client1', qos=0)

        subscribers = topic_tree.match('home/temperature')
        assert 'client1' in subscribers
        assert subscribers['client1'] == 0

    def test_subscribe_multiple_clients_same_topic(self, topic_tree):
        """Test multiple clients subscribing to same topic."""
        topic_tree.subscribe('sensor/data', 'client1', qos=0)
        topic_tree.subscribe('sensor/data', 'client2', qos=1)

        subscribers = topic_tree.match('sensor/data')
        assert len(subscribers) == 2
        assert subscribers['client1'] == 0
        assert subscribers['client2'] == 1

    def test_subscribe_bytes_topic(self, topic_tree):
        """Test subscribing with bytes topic."""
        topic_tree.subscribe(b'test/topic', 'client1', qos=2)

        subscribers = topic_tree.match(b'test/topic')
        assert 'client1' in subscribers
        assert subscribers['client1'] == 2

    def test_unsubscribe_existing(self, topic_tree):
        """Test unsubscribing from existing subscription."""
        topic_tree.subscribe('test/topic', 'client1', qos=0)
        result = topic_tree.unsubscribe('test/topic', 'client1')

        assert result is True
        subscribers = topic_tree.match('test/topic')
        assert 'client1' not in subscribers

    def test_unsubscribe_nonexistent_topic(self, topic_tree):
        """Test unsubscribing from non-existent topic returns False."""
        result = topic_tree.unsubscribe('nonexistent', 'client1')
        assert result is False

    def test_unsubscribe_nonexistent_client(self, topic_tree):
        """Test unsubscribing non-existent client returns False."""
        topic_tree.subscribe('test/topic', 'client1', qos=0)
        result = topic_tree.unsubscribe('test/topic', 'client2')
        assert result is False

    def test_unsubscribe_all_removes_all_subscriptions(self, topic_tree):
        """Test unsubscribe_all removes all subscriptions for a client."""
        topic_tree.subscribe('topic1', 'client1', qos=0)
        topic_tree.subscribe('topic2', 'client1', qos=1)
        topic_tree.subscribe('topic3', 'client1', qos=2)
        topic_tree.subscribe('topic1', 'client2', qos=0)

        topic_tree.unsubscribe_all('client1')

        assert 'client1' not in topic_tree.match('topic1')
        assert 'client1' not in topic_tree.match('topic2')
        assert 'client1' not in topic_tree.match('topic3')
        # client2 should still be subscribed
        assert 'client2' in topic_tree.match('topic1')


class TestTopicTreeMatching:
    """Test topic matching with wildcards."""

    def test_match_exact_topic(self, topic_tree):
        """Test matching exact topic."""
        topic_tree.subscribe('home/temperature', 'client1', qos=0)

        subscribers = topic_tree.match('home/temperature')
        assert 'client1' in subscribers

        subscribers = topic_tree.match('home/humidity')
        assert 'client1' not in subscribers

    def test_match_plus_wildcard_single_level(self, topic_tree):
        """Test matching + wildcard (single level)."""
        topic_tree.subscribe('home/+/temperature', 'client1', qos=0)

        assert 'client1' in topic_tree.match('home/kitchen/temperature')
        assert 'client1' in topic_tree.match('home/bedroom/temperature')
        assert 'client1' not in topic_tree.match('home/kitchen/humidity')
        assert 'client1' not in topic_tree.match('home/kitchen/living/temperature')

    def test_match_plus_wildcard_only(self, topic_tree):
        """Test matching + wildcard alone."""
        topic_tree.subscribe('+', 'client1', qos=0)

        assert 'client1' in topic_tree.match('test')
        assert 'client1' in topic_tree.match('home')
        assert 'client1' not in topic_tree.match('home/temperature')

    def test_match_hash_wildcard_multi_level(self, topic_tree):
        """Test matching # wildcard (multi-level)."""
        topic_tree.subscribe('home/#', 'client1', qos=0)

        assert 'client1' in topic_tree.match('home/temperature')
        assert 'client1' in topic_tree.match('home/kitchen/temperature')
        assert 'client1' in topic_tree.match('home/a/b/c/d')
        assert 'client1' not in topic_tree.match('office/temperature')

    def test_match_hash_wildcard_only(self, topic_tree):
        """Test matching # wildcard alone matches everything."""
        topic_tree.subscribe('#', 'client1', qos=0)

        assert 'client1' in topic_tree.match('anything')
        assert 'client1' in topic_tree.match('home/temperature')
        assert 'client1' in topic_tree.match('a/b/c/d/e')

    def test_match_multiple_wildcards(self, topic_tree):
        """Test matching with multiple + wildcards."""
        topic_tree.subscribe('+/+/temperature', 'client1', qos=0)

        assert 'client1' in topic_tree.match('home/kitchen/temperature')
        assert 'client1' in topic_tree.match('office/desk/temperature')
        assert 'client1' not in topic_tree.match('home/temperature')
        assert 'client1' not in topic_tree.match('home/kitchen/desk/temperature')

    def test_match_sys_topics_not_matched_by_hash_at_first_level(self, topic_tree):
        """Test $SYS topics not matched by # wildcard at first level."""
        topic_tree.subscribe('#', 'client1', qos=0)

        # $SYS topics should NOT match # at first level
        subscribers = topic_tree.match('$SYS/broker/uptime')
        assert 'client1' not in subscribers

        # Regular topics should match
        subscribers = topic_tree.match('regular/topic')
        assert 'client1' in subscribers

    def test_match_sys_topics_not_matched_by_plus_at_first_level(self, topic_tree):
        """Test $SYS topics not matched by + wildcard at first level."""
        topic_tree.subscribe('+/broker/uptime', 'client1', qos=0)

        # $SYS should NOT match + at first level
        subscribers = topic_tree.match('$SYS/broker/uptime')
        assert 'client1' not in subscribers

        # Regular topics should match
        subscribers = topic_tree.match('regular/broker/uptime')
        assert 'client1' in subscribers

    def test_match_sys_topics_exact_subscription(self, topic_tree):
        """Test $SYS topics can be subscribed to explicitly."""
        topic_tree.subscribe('$SYS/broker/uptime', 'client1', qos=0)

        subscribers = topic_tree.match('$SYS/broker/uptime')
        assert 'client1' in subscribers

    def test_match_empty_topic_levels(self, topic_tree):
        """Test matching topics with empty levels."""
        topic_tree.subscribe('home//temperature', 'client1', qos=0)

        subscribers = topic_tree.match('home//temperature')
        assert 'client1' in subscribers

        subscribers = topic_tree.match('home/kitchen/temperature')
        assert 'client1' not in subscribers


class TestTopicTreeRetained:
    """Test retained message management."""

    def test_set_retained_message(self, topic_tree):
        """Test setting retained message."""
        topic_tree.set_retained('test/topic', b'payload', qos=1)

        retained = topic_tree.get_retained('test/topic')
        assert retained is not None
        assert retained[0] == b'test/topic'
        assert retained[1] == b'payload'
        assert retained[2] == 1

    def test_set_retained_empty_payload_clears(self, topic_tree):
        """Test setting retained with empty payload clears it."""
        topic_tree.set_retained('test/topic', b'payload', qos=1)
        topic_tree.set_retained('test/topic', b'', qos=0)

        retained = topic_tree.get_retained('test/topic')
        assert retained is None

    def test_set_retained_string_topic(self, topic_tree):
        """Test setting retained message with string topic."""
        topic_tree.set_retained('string/topic', b'data', qos=0)

        retained = topic_tree.get_retained('string/topic')
        assert retained is not None
        assert retained[0] == b'string/topic'

    def test_get_retained_nonexistent(self, topic_tree):
        """Test getting retained message for non-existent topic."""
        retained = topic_tree.get_retained('nonexistent')
        assert retained is None

    def test_get_retained_matching_exact(self, topic_tree):
        """Test getting retained messages matching exact topic filter."""
        topic_tree.set_retained('test/topic', b'payload', qos=0)

        retained = topic_tree.get_retained_matching('test/topic')
        assert len(retained) == 1
        assert retained[0] == (b'test/topic', b'payload', 0)

    def test_get_retained_matching_plus_wildcard(self, topic_tree):
        """Test getting retained messages matching + wildcard."""
        topic_tree.set_retained('home/kitchen/temp', b'20', qos=0)
        topic_tree.set_retained('home/bedroom/temp', b'18', qos=0)
        topic_tree.set_retained('home/kitchen/humidity', b'60', qos=0)

        retained = topic_tree.get_retained_matching('home/+/temp')
        assert len(retained) == 2
        topics = [r[0] for r in retained]
        assert b'home/kitchen/temp' in topics
        assert b'home/bedroom/temp' in topics

    def test_get_retained_matching_hash_wildcard(self, topic_tree):
        """Test getting retained messages matching # wildcard."""
        topic_tree.set_retained('sensor/temp', b'25', qos=0)
        topic_tree.set_retained('sensor/humidity', b'50', qos=0)
        topic_tree.set_retained('sensor/kitchen/temp', b'22', qos=0)

        retained = topic_tree.get_retained_matching('sensor/#')
        assert len(retained) == 3

    def test_get_retained_matching_sys_topics_filtered(self, topic_tree):
        """Test # wildcard at first level doesn't match $SYS retained messages."""
        topic_tree.set_retained('$SYS/broker/uptime', b'100', qos=0)
        topic_tree.set_retained('regular/topic', b'data', qos=0)

        retained = topic_tree.get_retained_matching('#')
        topics = [r[0].decode('utf-8') for r in retained]

        assert 'regular/topic' in topics
        assert '$SYS/broker/uptime' not in topics

    def test_get_retained_count(self, topic_tree):
        """Test counting retained messages."""
        assert topic_tree.get_retained_count() == 0

        topic_tree.set_retained('topic1', b'data1', qos=0)
        topic_tree.set_retained('topic2', b'data2', qos=0)
        topic_tree.set_retained('topic3', b'data3', qos=0)

        assert topic_tree.get_retained_count() == 3

        # Clearing one should decrement count
        topic_tree.set_retained('topic1', b'', qos=0)
        assert topic_tree.get_retained_count() == 2


class TestTopicTreeStats:
    """Test topic tree statistics."""

    def test_get_subscription_count_empty(self, topic_tree):
        """Test subscription count on empty tree."""
        assert topic_tree.get_subscription_count() == 0

    def test_get_subscription_count_single_subscription(self, topic_tree):
        """Test subscription count with single subscription."""
        topic_tree.subscribe('test/topic', 'client1', qos=0)
        assert topic_tree.get_subscription_count() == 1

    def test_get_subscription_count_multiple_clients_same_topic(self, topic_tree):
        """Test subscription count with multiple clients on same topic."""
        topic_tree.subscribe('test/topic', 'client1', qos=0)
        topic_tree.subscribe('test/topic', 'client2', qos=0)
        assert topic_tree.get_subscription_count() == 2

    def test_get_subscription_count_multiple_topics(self, topic_tree):
        """Test subscription count across multiple topics."""
        topic_tree.subscribe('topic1', 'client1', qos=0)
        topic_tree.subscribe('topic2', 'client1', qos=0)
        topic_tree.subscribe('topic3', 'client2', qos=0)
        assert topic_tree.get_subscription_count() == 3

    def test_get_retained_count_empty(self, topic_tree):
        """Test retained count on empty tree."""
        assert topic_tree.get_retained_count() == 0

    def test_get_retained_count_multiple_messages(self, topic_tree):
        """Test retained count with multiple messages."""
        topic_tree.set_retained('topic1', b'data1', qos=0)
        topic_tree.set_retained('topic2', b'data2', qos=0)
        topic_tree.set_retained('topic3', b'data3', qos=0)
        assert topic_tree.get_retained_count() == 3


class TestTopicTreePrune:
    """Test topic tree pruning of empty nodes."""

    def test_prune_empty_leaf(self, topic_tree):
        """Test pruning removes empty leaf nodes."""
        topic_tree.subscribe('a/b/c', 'client1', 0)
        topic_tree.unsubscribe('a/b/c', 'client1')

        topic_tree.prune()

        # All nodes should be gone since they have no subscribers/retained
        assert topic_tree.root.children is None or 'a' not in (topic_tree.root.children or {})

    def test_prune_preserves_subscribers(self, topic_tree):
        """Test pruning preserves nodes with subscribers."""
        topic_tree.subscribe('a/b', 'client1', 0)
        topic_tree.subscribe('a/b/c', 'client2', 0)
        topic_tree.unsubscribe('a/b/c', 'client2')

        topic_tree.prune()

        # a/b should still exist (has subscriber)
        subs = topic_tree.match('a/b')
        assert 'client1' in subs

    def test_prune_preserves_retained(self, topic_tree):
        """Test pruning preserves nodes with retained messages."""
        topic_tree.set_retained('x/y/z', b'data', 0)
        topic_tree.subscribe('x/y/z', 'client1', 0)
        topic_tree.unsubscribe('x/y/z', 'client1')

        topic_tree.prune()

        # Node should still exist due to retained message
        retained = topic_tree.get_retained('x/y/z')
        assert retained is not None

    def test_prune_empty_tree(self, topic_tree):
        """Test pruning an empty tree does not error."""
        topic_tree.prune()
        # Should not raise

    def test_prune_chain_removal(self, topic_tree):
        """Test pruning removes entire chain of empty nodes."""
        topic_tree.subscribe('deep/path/to/topic', 'client1', 0)
        topic_tree.unsubscribe('deep/path/to/topic', 'client1')

        topic_tree.prune()

        # Entire chain deep/path/to/topic should be gone
        assert topic_tree.root.children is None or 'deep' not in (topic_tree.root.children or {})
        assert topic_tree.get_subscription_count() == 0
