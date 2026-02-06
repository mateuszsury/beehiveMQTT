"""
Topic Tree with wildcard matching for BeehiveMQTT.

Implements a trie-based structure for efficient MQTT topic subscription
and matching with support for '+' (single-level) and '#' (multi-level) wildcards.
"""


class TopicNode:
    """Node in the topic tree trie structure."""
    __slots__ = ('children', 'subscribers', 'retained')

    def __init__(self):
        self.children = None     # str -> TopicNode (lazy, None until first child)
        self.subscribers = {}    # client_id -> granted_qos
        self.retained = None     # (topic_bytes, payload_bytes, qos) or None


def _ensure_children(node):
    """Create children dict on first use (lazy initialization)."""
    if node.children is None:
        node.children = {}
    return node.children


class TopicTree:
    """
    Topic tree for MQTT subscription and retained message management.

    Uses a trie structure where each level is separated by '/'.
    Supports MQTT wildcards:
    - '+' matches exactly one level
    - '#' matches zero or more levels

    Special rule: Topics starting with '$' are not matched by wildcards
    at the first level.
    """

    def __init__(self):
        self.root = TopicNode()

    def _split_topic(self, topic):
        """Convert topic to list of string levels."""
        if isinstance(topic, bytes):
            topic = topic.decode('utf-8')
        return topic.split('/')

    def subscribe(self, topic_filter, client_id, qos):
        """
        Subscribe a client to a topic filter.

        Args:
            topic_filter: bytes or str, may contain '+' or '#' wildcards
            client_id: str, unique client identifier
            qos: int, granted QoS level (0, 1, or 2)
        """
        levels = self._split_topic(topic_filter)
        node = self.root

        # Navigate/create nodes for each level
        for level in levels:
            children = _ensure_children(node)
            if level not in children:
                children[level] = TopicNode()
            node = children[level]

        # Set subscription at leaf node
        node.subscribers[client_id] = qos

    def unsubscribe(self, topic_filter, client_id):
        """
        Unsubscribe a client from a topic filter.

        Args:
            topic_filter: bytes or str
            client_id: str

        Returns:
            bool: True if subscription was found and removed, False otherwise
        """
        levels = self._split_topic(topic_filter)
        node = self.root

        # Navigate to the leaf node
        for level in levels:
            if not node.children or level not in node.children:
                return False
            node = node.children[level]

        # Remove subscription
        if client_id in node.subscribers:
            del node.subscribers[client_id]
            return True
        return False

    def unsubscribe_all(self, client_id):
        """
        Remove all subscriptions for a client.

        Uses iterative DFS to avoid stack overflow on deep trees.

        Args:
            client_id: str
        """
        stack = [self.root]

        while stack:
            node = stack.pop()

            # Remove from subscribers at this node
            if client_id in node.subscribers:
                del node.subscribers[client_id]

            # Add all children to stack
            if node.children:
                for child in node.children.values():
                    stack.append(child)

    def match(self, topic_name):
        """
        Find all subscribers matching a concrete topic name.

        Args:
            topic_name: bytes or str, concrete topic (no wildcards)

        Returns:
            dict: {client_id: granted_qos} for all matching subscribers
        """
        levels = self._split_topic(topic_name)
        result = {}

        # Stack items: (node, level_index)
        stack = [(self.root, 0)]

        while stack:
            node, level_idx = stack.pop()

            # If we've matched all levels
            if level_idx == len(levels):
                # Collect subscribers at this exact node
                result.update(node.subscribers)
                # Check for '#' wildcard (matches zero or more)
                if node.children and '#' in node.children:
                    result.update(node.children['#'].subscribers)
                continue

            current_level = levels[level_idx]
            is_first_level = (level_idx == 0)
            is_system_topic = (is_first_level and current_level.startswith('$'))

            if not node.children:
                continue

            # 1. Exact match
            if current_level in node.children:
                stack.append((node.children[current_level], level_idx + 1))

            # 2. '+' wildcard (matches exactly one level)
            # Don't match system topics at first level
            if '+' in node.children and not is_system_topic:
                stack.append((node.children['+'], level_idx + 1))

            # 3. '#' wildcard (matches zero or more levels)
            # Don't match system topics at first level
            if '#' in node.children and not is_system_topic:
                result.update(node.children['#'].subscribers)

        return result

    def set_retained(self, topic_name, payload, qos):
        """
        Set or clear a retained message for a topic.

        Args:
            topic_name: bytes or str, concrete topic (no wildcards)
            payload: bytes, message payload (empty to clear)
            qos: int, QoS level
        """
        levels = self._split_topic(topic_name)
        node = self.root

        # Navigate/create nodes
        for level in levels:
            children = _ensure_children(node)
            if level not in children:
                children[level] = TopicNode()
            node = children[level]

        # Convert topic_name to bytes for storage
        if isinstance(topic_name, str):
            topic_name = topic_name.encode('utf-8')

        # Clear or set retained message
        if not payload or len(payload) == 0:
            node.retained = None
        else:
            node.retained = (topic_name, payload, qos)

    def get_retained(self, topic_name):
        """
        Get retained message for an exact topic.

        Args:
            topic_name: bytes or str, concrete topic

        Returns:
            (topic_bytes, payload, qos) tuple or None
        """
        levels = self._split_topic(topic_name)
        node = self.root

        for level in levels:
            if not node.children or level not in node.children:
                return None
            node = node.children[level]

        return node.retained

    def get_retained_matching(self, topic_filter):
        """
        Get all retained messages matching a topic filter.

        Args:
            topic_filter: bytes or str, may contain wildcards

        Returns:
            list: [(topic_bytes, payload, qos), ...]
        """
        levels = self._split_topic(topic_filter)
        result = []

        # Stack items: (node, level_index)
        stack = [(self.root, 0)]

        while stack:
            node, level_idx = stack.pop()

            # If we've matched all filter levels
            if level_idx == len(levels):
                # Collect retained at this node
                if node.retained:
                    result.append(node.retained)
                continue

            filter_level = levels[level_idx]
            is_first_level = (level_idx == 0)

            # Handle wildcards in the filter
            if filter_level == '#':
                # '#' matches everything from here down
                # Use DFS to collect all retained messages
                dfs_stack = [node]
                while dfs_stack:
                    n = dfs_stack.pop()
                    if n.retained:
                        # Skip system topics if '#' is at first level
                        if is_first_level:
                            topic_str = n.retained[0].decode('utf-8')
                            if topic_str.startswith('$'):
                                continue
                        result.append(n.retained)
                    if n.children:
                        for child in n.children.values():
                            dfs_stack.append(child)
                continue

            if not node.children:
                continue

            if filter_level == '+':
                # '+' matches any single level (except $ at first level)
                for level_name, child in node.children.items():
                    if is_first_level and level_name.startswith('$'):
                        continue
                    stack.append((child, level_idx + 1))

            else:
                # Exact match
                if filter_level in node.children:
                    stack.append((node.children[filter_level], level_idx + 1))

        return result

    def get_subscription_count(self):
        """
        Count total number of subscriptions across all topics.

        Returns:
            int: Total subscription count
        """
        count = 0
        stack = [self.root]

        while stack:
            node = stack.pop()
            count += len(node.subscribers)

            if node.children:
                for child in node.children.values():
                    stack.append(child)

        return count

    def get_retained_count(self):
        """
        Count number of retained messages in the tree.

        Returns:
            int: Number of retained messages
        """
        count = 0
        stack = [self.root]

        while stack:
            node = stack.pop()
            if node.retained is not None:
                count += 1

            if node.children:
                for child in node.children.values():
                    stack.append(child)

        return count

    def prune(self):
        """
        Remove empty leaf nodes from the topic tree.

        Uses iterative post-order DFS. A node is removed if it has
        no children, no subscribers, and no retained message.
        """
        # Build parent map and post-order traversal
        # Stack items: (parent, key, node)
        work = []
        stack = [(None, None, self.root)]
        while stack:
            parent, key, node = stack.pop()
            work.append((parent, key, node))
            if node.children:
                for child_key, child_node in list(node.children.items()):
                    stack.append((node, child_key, child_node))

        # Process in reverse order (post-order: children before parents)
        for parent, key, node in reversed(work):
            if parent is None:
                continue  # Don't remove root
            if not node.children and not node.subscribers and node.retained is None:
                if parent.children and key in parent.children:
                    del parent.children[key]
