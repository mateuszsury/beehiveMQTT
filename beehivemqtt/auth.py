"""
Authentication and authorization module for BeehiveMQTT.

Provides pluggable authentication and authorization for MQTT broker.
Supports simple dict-based auth, ACL with topic patterns, and custom callbacks.
"""


class AuthProvider:
    """Base auth provider - allows everything by default."""

    def authenticate(self, client_id, username, password):
        """Returns True if authenticated."""
        return True

    def authorize_publish(self, client_id, topic):
        """Returns True if client can publish to topic."""
        return True

    def authorize_subscribe(self, client_id, topic_filter):
        """Returns max QoS (0-2) or -1 to deny."""
        return 2

    def cleanup_client(self, client_id):
        """Clean up any per-client state. Called on disconnect."""
        pass


class DictAuthProvider(AuthProvider):
    """Simple dict-based authentication {username: password}."""

    def __init__(self, users):
        """
        Initialize with users dict.

        Args:
            users: dict mapping username -> password
        """
        self.users = users

    def authenticate(self, client_id, username, password):
        """Authenticate using username/password lookup."""
        if username is None or password is None:
            return False
        return self.users.get(username) == password


class ACLAuthProvider(AuthProvider):
    """Role-based access control with topic patterns."""

    def __init__(self):
        """Initialize empty ACL provider."""
        self.users = {}       # username -> {password, role}
        self.acl_rules = []   # list of {role, pattern, publish, subscribe}
        self._client_roles = {}  # client_id -> role (set on auth)

    def add_user(self, username, password, role='default'):
        """Add a user with password and role."""
        self.users[username] = {'password': password, 'role': role}

    def add_acl(self, role, topic_pattern, publish=True, subscribe=True):
        """
        Add ACL rule for role and topic pattern.

        Args:
            role: User role name
            topic_pattern: MQTT topic pattern (supports +/# wildcards)
            publish: Allow publish to matching topics
            subscribe: Allow subscribe to matching topics
        """
        self.acl_rules.append({
            'role': role,
            'pattern': topic_pattern,
            'publish': publish,
            'subscribe': subscribe
        })

    def authenticate(self, client_id, username, password):
        """Authenticate and track client role."""
        if username is None:
            return False
        user = self.users.get(username)
        if user is None:
            return False
        if user['password'] != password:
            return False
        # Track client->role mapping for authorization
        self._client_roles[client_id] = user['role']
        return True

    def _get_role(self, client_id):
        """Look up role for connected client."""
        return self._client_roles.get(client_id, 'default')

    def authorize_publish(self, client_id, topic):
        """Check if client can publish to topic based on ACL rules."""
        role = self._get_role(client_id)
        for rule in self.acl_rules:
            if rule['role'] == role and self._match_pattern(rule['pattern'], topic):
                if rule['publish']:
                    return True
        return False

    def authorize_subscribe(self, client_id, topic_filter):
        """Check if client can subscribe to topic filter based on ACL rules."""
        role = self._get_role(client_id)
        for rule in self.acl_rules:
            if rule['role'] == role and self._match_pattern(rule['pattern'], topic_filter):
                if rule['subscribe']:
                    return 2  # Max QoS
        return -1  # Deny

    def cleanup_client(self, client_id):
        """Remove per-client role mapping to prevent memory leak."""
        if client_id in self._client_roles:
            del self._client_roles[client_id]

    def _match_pattern(self, pattern, topic):
        """
        Match ACL pattern against topic with MQTT wildcards.

        Supports:
            + = single level wildcard
            # = multi-level wildcard (must be last)
        """
        # Convert to strings if needed
        if isinstance(pattern, bytes):
            pattern = pattern.decode('utf-8')
        if isinstance(topic, bytes):
            topic = topic.decode('utf-8')

        p_levels = pattern.split('/')
        t_levels = topic.split('/')

        pi = 0
        ti = 0
        while pi < len(p_levels) and ti < len(t_levels):
            if p_levels[pi] == '#':
                return True  # Matches rest of topic
            if p_levels[pi] == '+' or p_levels[pi] == t_levels[ti]:
                pi += 1
                ti += 1
            else:
                return False
        return pi == len(p_levels) and ti == len(t_levels)


class CallbackAuthProvider(AuthProvider):
    """Delegates auth decisions to user-provided callbacks."""

    def __init__(self, on_authenticate=None, on_authorize_publish=None, on_authorize_subscribe=None):
        """
        Initialize with optional callbacks.

        Args:
            on_authenticate: callback(client_id, username, password) -> bool
            on_authorize_publish: callback(client_id, topic) -> bool
            on_authorize_subscribe: callback(client_id, topic_filter) -> int (QoS or -1)
        """
        self._on_authenticate = on_authenticate
        self._on_authorize_publish = on_authorize_publish
        self._on_authorize_subscribe = on_authorize_subscribe

    def authenticate(self, client_id, username, password):
        """Delegate to callback or allow by default."""
        if self._on_authenticate:
            return self._on_authenticate(client_id, username, password)
        return True

    def authorize_publish(self, client_id, topic):
        """Delegate to callback or allow by default."""
        if self._on_authorize_publish:
            return self._on_authorize_publish(client_id, topic)
        return True

    def authorize_subscribe(self, client_id, topic_filter):
        """Delegate to callback or allow by default."""
        if self._on_authorize_subscribe:
            return self._on_authorize_subscribe(client_id, topic_filter)
        return 2  # Max QoS
