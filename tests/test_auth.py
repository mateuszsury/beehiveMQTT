"""Tests for beehivemqtt.auth module."""

import pytest
from beehivemqtt.auth import (
    AuthProvider, DictAuthProvider, ACLAuthProvider, CallbackAuthProvider
)


class TestAuthProvider:
    """Test base AuthProvider class."""

    def test_authenticate_allows_all(self):
        """Test base AuthProvider allows all authentication."""
        auth = AuthProvider()

        assert auth.authenticate('client1', 'user1', 'pass1') is True
        assert auth.authenticate('client2', None, None) is True

    def test_authorize_publish_allows_all(self):
        """Test base AuthProvider allows all publish."""
        auth = AuthProvider()

        assert auth.authorize_publish('client1', b'test/topic') is True
        assert auth.authorize_publish('client2', b'any/topic') is True

    def test_authorize_subscribe_allows_all_max_qos(self):
        """Test base AuthProvider allows all subscribe with max QoS."""
        auth = AuthProvider()

        assert auth.authorize_subscribe('client1', b'test/topic') == 2
        assert auth.authorize_subscribe('client2', b'#') == 2

    def test_cleanup_client_noop(self):
        """Test base AuthProvider cleanup_client does nothing (no error)."""
        auth = AuthProvider()

        # Should not raise any exception
        auth.cleanup_client('client1')
        auth.cleanup_client('nonexistent')


class TestDictAuthProvider:
    """Test DictAuthProvider class."""

    def test_authenticate_valid_user(self):
        """Test authentication with valid credentials."""
        auth = DictAuthProvider({'user1': 'pass1', 'user2': 'pass2'})

        assert auth.authenticate('client1', 'user1', 'pass1') is True
        assert auth.authenticate('client2', 'user2', 'pass2') is True

    def test_authenticate_invalid_password(self):
        """Test authentication fails with invalid password."""
        auth = DictAuthProvider({'user1': 'pass1'})

        assert auth.authenticate('client1', 'user1', 'wrongpass') is False

    def test_authenticate_invalid_user(self):
        """Test authentication fails with non-existent user."""
        auth = DictAuthProvider({'user1': 'pass1'})

        assert auth.authenticate('client1', 'user2', 'pass2') is False

    def test_authenticate_none_username(self):
        """Test authentication fails with None username."""
        auth = DictAuthProvider({'user1': 'pass1'})

        assert auth.authenticate('client1', None, 'pass1') is False

    def test_authenticate_none_password(self):
        """Test authentication fails with None password."""
        auth = DictAuthProvider({'user1': 'pass1'})

        assert auth.authenticate('client1', 'user1', None) is False

    def test_authorize_publish_always_true(self):
        """Test DictAuthProvider inherits authorize_publish (allows all)."""
        auth = DictAuthProvider({'user1': 'pass1'})

        assert auth.authorize_publish('client1', b'test/topic') is True

    def test_authorize_subscribe_always_max_qos(self):
        """Test DictAuthProvider inherits authorize_subscribe (max QoS)."""
        auth = DictAuthProvider({'user1': 'pass1'})

        assert auth.authorize_subscribe('client1', b'test/topic') == 2


class TestACLAuthProvider:
    """Test ACLAuthProvider class."""

    def test_add_user(self):
        """Test adding a user."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='admin')

        assert 'user1' in auth.users
        assert auth.users['user1']['password'] == 'pass1'
        assert auth.users['user1']['role'] == 'admin'

    def test_add_user_default_role(self):
        """Test adding user with default role."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1')

        assert auth.users['user1']['role'] == 'default'

    def test_add_acl_rule(self):
        """Test adding ACL rule."""
        auth = ACLAuthProvider()
        auth.add_acl('admin', 'admin/#', publish=True, subscribe=True)

        assert len(auth.acl_rules) == 1
        assert auth.acl_rules[0]['role'] == 'admin'
        assert auth.acl_rules[0]['pattern'] == 'admin/#'
        assert auth.acl_rules[0]['publish'] is True
        assert auth.acl_rules[0]['subscribe'] is True

    def test_authenticate_valid_user(self):
        """Test authenticating valid user and tracking role."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='admin')

        result = auth.authenticate('client1', 'user1', 'pass1')

        assert result is True
        assert auth._client_roles['client1'] == 'admin'

    def test_authenticate_invalid_password(self):
        """Test authentication fails with wrong password."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='admin')

        result = auth.authenticate('client1', 'user1', 'wrongpass')

        assert result is False
        assert 'client1' not in auth._client_roles

    def test_authenticate_none_username(self):
        """Test authentication fails with None username."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1')

        result = auth.authenticate('client1', None, 'pass1')

        assert result is False

    def test_authenticate_unknown_user(self):
        """Test authentication fails with unknown user."""
        auth = ACLAuthProvider()

        result = auth.authenticate('client1', 'unknown', 'pass')

        assert result is False

    def test_authorize_publish_with_matching_rule(self):
        """Test authorize_publish allows with matching ACL rule."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='sensor')
        auth.add_acl('sensor', 'sensor/#', publish=True, subscribe=False)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_publish('client1', b'sensor/temperature') is True

    def test_authorize_publish_denies_without_matching_rule(self):
        """Test authorize_publish denies without matching ACL rule."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='sensor')
        auth.add_acl('sensor', 'sensor/#', publish=True, subscribe=False)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_publish('client1', b'admin/command') is False

    def test_authorize_publish_denies_when_rule_publish_false(self):
        """Test authorize_publish denies when ACL rule has publish=False."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='reader')
        auth.add_acl('reader', 'data/#', publish=False, subscribe=True)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_publish('client1', b'data/sensor') is False

    def test_authorize_subscribe_with_matching_rule(self):
        """Test authorize_subscribe allows with matching ACL rule."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='sensor')
        auth.add_acl('sensor', 'sensor/#', publish=True, subscribe=True)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_subscribe('client1', b'sensor/temperature') == 2

    def test_authorize_subscribe_denies_without_matching_rule(self):
        """Test authorize_subscribe denies without matching ACL rule."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='sensor')
        auth.add_acl('sensor', 'sensor/#', publish=True, subscribe=True)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_subscribe('client1', b'admin/command') == -1

    def test_authorize_subscribe_denies_when_rule_subscribe_false(self):
        """Test authorize_subscribe denies when ACL rule has subscribe=False."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='writer')
        auth.add_acl('writer', 'data/#', publish=True, subscribe=False)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_subscribe('client1', b'data/sensor') == -1

    def test_acl_pattern_matching_exact(self):
        """Test ACL pattern matching with exact topic."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='test')
        auth.add_acl('test', 'exact/topic', publish=True, subscribe=True)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_publish('client1', b'exact/topic') is True
        assert auth.authorize_publish('client1', b'exact/other') is False

    def test_acl_pattern_matching_plus_wildcard(self):
        """Test ACL pattern matching with + wildcard."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='test')
        auth.add_acl('test', 'home/+/temp', publish=True, subscribe=True)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_publish('client1', b'home/kitchen/temp') is True
        assert auth.authorize_publish('client1', b'home/bedroom/temp') is True
        assert auth.authorize_publish('client1', b'home/kitchen/humidity') is False

    def test_acl_pattern_matching_hash_wildcard(self):
        """Test ACL pattern matching with # wildcard."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='test')
        auth.add_acl('test', 'sensor/#', publish=True, subscribe=True)

        auth.authenticate('client1', 'user1', 'pass1')

        assert auth.authorize_publish('client1', b'sensor/temp') is True
        assert auth.authorize_publish('client1', b'sensor/kitchen/temp') is True
        assert auth.authorize_publish('client1', b'sensor/a/b/c') is True
        assert auth.authorize_publish('client1', b'other/temp') is False

    def test_cleanup_client_removes_role(self):
        """Test cleanup_client removes the client's role from _client_roles."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='admin')

        auth.authenticate('client1', 'user1', 'pass1')
        assert 'client1' in auth._client_roles

        auth.cleanup_client('client1')
        assert 'client1' not in auth._client_roles

    def test_cleanup_client_nonexistent(self):
        """Test cleanup_client on non-existent client doesn't error."""
        auth = ACLAuthProvider()

        # Should not raise any exception
        auth.cleanup_client('nonexistent_client')

    def test_authorize_with_unknown_client_uses_default_role(self):
        """Test client not in _client_roles gets 'default' role."""
        auth = ACLAuthProvider()
        auth.add_acl('default', 'public/#', publish=True, subscribe=True)

        # Client never authenticated, so not in _client_roles
        assert auth.authorize_publish('unknown_client', b'public/data') is True
        assert auth.authorize_subscribe('unknown_client', b'public/data') == 2

        # But should be denied for topics not covered by default role
        assert auth.authorize_publish('unknown_client', b'private/data') is False
        assert auth.authorize_subscribe('unknown_client', b'private/data') == -1

    def test_multiple_acl_rules_first_match(self):
        """Test with multiple rules, first matching allow rule wins."""
        auth = ACLAuthProvider()
        auth.add_user('user1', 'pass1', role='mixed')

        # First rule: allows publish on 'data/#', denies subscribe
        auth.add_acl('mixed', 'data/#', publish=True, subscribe=False)
        # Second rule: denies publish on 'data/#', allows subscribe
        auth.add_acl('mixed', 'data/#', publish=False, subscribe=True)

        auth.authenticate('client1', 'user1', 'pass1')

        # Publish: first rule matches with publish=True, returns True immediately
        assert auth.authorize_publish('client1', b'data/sensor') is True
        # Subscribe: first rule matches but subscribe=False, skips;
        # second rule matches with subscribe=True, returns 2
        assert auth.authorize_subscribe('client1', b'data/sensor') == 2


class TestCallbackAuthProvider:
    """Test CallbackAuthProvider class."""

    def test_authenticate_with_callback(self):
        """Test authentication delegates to callback."""
        def auth_callback(client_id, username, password):
            return username == 'valid' and password == 'secret'

        auth = CallbackAuthProvider(on_authenticate=auth_callback)

        assert auth.authenticate('client1', 'valid', 'secret') is True
        assert auth.authenticate('client2', 'valid', 'wrong') is False

    def test_authenticate_without_callback_allows_all(self):
        """Test authentication without callback allows all."""
        auth = CallbackAuthProvider()

        assert auth.authenticate('client1', 'any', 'pass') is True

    def test_authorize_publish_with_callback(self):
        """Test authorize_publish delegates to callback."""
        def pub_callback(client_id, topic):
            return topic.startswith(b'allowed/')

        auth = CallbackAuthProvider(on_authorize_publish=pub_callback)

        assert auth.authorize_publish('client1', b'allowed/topic') is True
        assert auth.authorize_publish('client1', b'denied/topic') is False

    def test_authorize_publish_without_callback_allows_all(self):
        """Test authorize_publish without callback allows all."""
        auth = CallbackAuthProvider()

        assert auth.authorize_publish('client1', b'any/topic') is True

    def test_authorize_subscribe_with_callback(self):
        """Test authorize_subscribe delegates to callback."""
        def sub_callback(client_id, topic_filter):
            if topic_filter.startswith(b'admin/'):
                return -1  # Deny
            return 1  # Allow with QoS 1

        auth = CallbackAuthProvider(on_authorize_subscribe=sub_callback)

        assert auth.authorize_subscribe('client1', b'public/topic') == 1
        assert auth.authorize_subscribe('client1', b'admin/command') == -1

    def test_authorize_subscribe_without_callback_returns_max_qos(self):
        """Test authorize_subscribe without callback returns max QoS."""
        auth = CallbackAuthProvider()

        assert auth.authorize_subscribe('client1', b'any/topic') == 2

    def test_all_callbacks_together(self):
        """Test CallbackAuthProvider with all callbacks."""
        def auth_cb(client_id, username, password):
            return username == 'user1'

        def pub_cb(client_id, topic):
            return topic == b'allowed'

        def sub_cb(client_id, topic_filter):
            return 2 if topic_filter == b'allowed' else -1

        auth = CallbackAuthProvider(
            on_authenticate=auth_cb,
            on_authorize_publish=pub_cb,
            on_authorize_subscribe=sub_cb
        )

        assert auth.authenticate('c1', 'user1', 'any') is True
        assert auth.authenticate('c1', 'user2', 'any') is False
        assert auth.authorize_publish('c1', b'allowed') is True
        assert auth.authorize_publish('c1', b'denied') is False
        assert auth.authorize_subscribe('c1', b'allowed') == 2
        assert auth.authorize_subscribe('c1', b'denied') == -1

    def test_authenticate_callback_exception_propagates(self):
        """Test if authenticate callback raises, exception propagates."""
        def bad_callback(client_id, username, password):
            raise ValueError("auth failure")

        auth = CallbackAuthProvider(on_authenticate=bad_callback)

        with pytest.raises(ValueError, match="auth failure"):
            auth.authenticate('client1', 'user', 'pass')

    def test_authorize_publish_callback_returns_false(self):
        """Test callback returning False denies publish."""
        def deny_all(client_id, topic):
            return False

        auth = CallbackAuthProvider(on_authorize_publish=deny_all)

        assert auth.authorize_publish('client1', b'any/topic') is False
        assert auth.authorize_publish('client2', b'other/topic') is False

    def test_authorize_subscribe_callback_returns_negative(self):
        """Test callback returning -1 denies subscribe."""
        def deny_all(client_id, topic_filter):
            return -1

        auth = CallbackAuthProvider(on_authorize_subscribe=deny_all)

        assert auth.authorize_subscribe('client1', b'any/topic') == -1
        assert auth.authorize_subscribe('client2', b'other/topic') == -1
