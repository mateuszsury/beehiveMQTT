"""
Retained message store for BeehiveMQTT.

Provides a high-level interface for managing retained messages with
size limits. Actual storage is delegated to TopicTree nodes.
"""


class RetainedStore:
    """Manages retained messages with size limits and LRU eviction.

    Retained messages are stored in the TopicTree (TopicNode.retained).
    This class provides limit enforcement, LRU eviction, and query operations.
    """

    def __init__(self, topic_tree, config):
        """Initialize retained message store.

        Args:
            topic_tree: TopicTree instance (delegates storage to it)
            config: BrokerConfig with max_retained_messages, retain_enabled
        """
        self.topic_tree = topic_tree
        self.config = config
        self._lru_order = []  # list of topic keys (most recent at end)

    def _touch_lru(self, topic_key):
        """Move topic to end of LRU list (most recently used)."""
        try:
            self._lru_order.remove(topic_key)
        except ValueError:
            pass
        self._lru_order.append(topic_key)

    def _remove_lru(self, topic_key):
        """Remove topic from LRU list."""
        try:
            self._lru_order.remove(topic_key)
        except ValueError:
            pass

    def set(self, topic, payload, qos):
        """Set or clear a retained message with LRU eviction.

        Args:
            topic: Topic name (bytes or str)
            payload: Message payload (bytes). Empty payload clears retained.
            qos: QoS level (int)

        Returns:
            bool: True if set/cleared, False if disabled
        """
        if not self.config.retain_enabled:
            return False

        # Normalize topic key for LRU tracking
        if isinstance(topic, bytes):
            topic_key = topic.decode('utf-8')
        else:
            topic_key = topic

        # Empty payload clears retained - always allow
        if not payload or len(payload) == 0:
            self.topic_tree.set_retained(topic, b'', 0)
            self._remove_lru(topic_key)
            return True

        # Check if at limit (unless replacing existing)
        existing = self.topic_tree.get_retained(topic)

        if existing is None:
            current_count = self.topic_tree.get_retained_count()
            if current_count >= self.config.max_retained_messages:
                # Evict oldest (LRU) entry
                if self._lru_order:
                    evict_key = self._lru_order.pop(0)
                    self.topic_tree.set_retained(evict_key, b'', 0)

        self.topic_tree.set_retained(topic, payload, qos)
        self._touch_lru(topic_key)
        return True

    def get_matching(self, topic_filter):
        """Get all retained messages matching a topic filter.

        Args:
            topic_filter: Topic filter (bytes or str), may contain wildcards

        Returns:
            list: [(topic_bytes, payload, qos), ...]
        """
        if not self.config.retain_enabled:
            return []
        return self.topic_tree.get_retained_matching(topic_filter)

    def clear(self, topic=None):
        """Clear retained message(s).

        Args:
            topic: Specific topic (bytes/str) to clear. If None, clear ALL retained.
        """
        if topic is not None:
            self.topic_tree.set_retained(topic, b'', 0)
            if isinstance(topic, bytes):
                self._remove_lru(topic.decode('utf-8'))
            else:
                self._remove_lru(topic)
        else:
            self._clear_all()
            self._lru_order = []

    def _clear_all(self):
        """Clear all retained messages from topic tree.

        Iterative DFS walk to avoid recursion on embedded systems.
        """
        stack = [self.topic_tree.root]
        while stack:
            node = stack.pop()
            if node.retained is not None:
                node.retained = None
            # Add children to stack
            if node.children:
                for child in node.children.values():
                    stack.append(child)

    def count(self):
        """Get number of retained messages currently stored.

        Returns:
            int: Count of retained messages
        """
        return self.topic_tree.get_retained_count()
