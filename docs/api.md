# API Reference

Complete API documentation for BeehiveMQTT classes and methods.

## Table of Contents

- [MQTTBroker](#mqttbroker)
- [BeehiveBrokerSimple](#beehivebrokersimple)
- [BrokerConfig](#brokerconfig)
- [MessageContext](#messagecontext)
- [Authentication Classes](#authentication-classes)
- [Topic and Routing](#topic-and-routing)
- [Error Classes](#error-classes)

---

## MQTTBroker

Full-featured MQTT 3.1.1 broker with QoS 0/1/2, authentication, logging, statistics, and memory management.

### Constructor

```python
MQTTBroker(config=None, auth=None)
```

**Parameters:**
- `config` (BrokerConfig): Configuration object. If None, uses defaults.
- `auth` (AuthProvider): Authentication handler. If None, allows all connections (unless `allow_anonymous=False`).

**Example:**
```python
from beehivemqtt import MQTTBroker, BrokerConfig, DictAuthProvider

config = BrokerConfig(port=1883, max_clients=20)
auth = DictAuthProvider({'user1': 'pass1', 'user2': 'pass2'})
broker = MQTTBroker(config=config, auth=auth)
```

### Core Methods

#### serve()

```python
async def serve()
```

Start the MQTT broker server. This is the main entry point. Blocks until `shutdown()` is called.

**Example:**
```python
import asyncio
asyncio.run(broker.serve())
```

#### publish()

```python
async def publish(topic, payload, qos=0, retain=False)
```

Publish a message from the broker itself (internal publish).

**Parameters:**
- `topic` (bytes or str): Topic name
- `payload` (bytes or str): Message payload
- `qos` (int): QoS level (0, 1, or 2)
- `retain` (bool): Retain flag

**Example:**
```python
await broker.publish('status/broker', 'online', qos=1, retain=True)
```

#### shutdown()

```python
async def shutdown()
```

Shutdown the broker and close all connections. Disconnects all clients, closes the server, and cancels background tasks.

#### disconnect_client()

```python
async def disconnect_client(client_id, graceful=True)
```

Forcefully disconnect a client by ID.

**Parameters:**
- `client_id` (str): Client identifier
- `graceful` (bool): If True, treat as clean disconnect (no will message)

**Returns:** `True` if client was found and disconnected, `False` otherwise.

### Information Methods

#### get_clients()

```python
def get_clients()
```

Get list of connected client info dictionaries.

**Returns:** List of dicts with keys:
- `client_id` (str)
- `username` (str or None)
- `connected` (bool)
- `subscriptions` (list of str)
- `keep_alive` (int)

**Example:**
```python
for client in broker.get_clients():
    print("%s: %d subscriptions" % (client['client_id'], len(client['subscriptions'])))
```

#### get_stats()

```python
def get_stats()
```

Get broker statistics as a dictionary.

**Returns:** Dict with keys:
- `uptime` (int): Uptime in seconds
- `clients_connected` (int): Number of connected clients
- `clients_total` (int): Total number of sessions
- `messages_received` (int): Total messages received
- `messages_sent` (int): Total messages sent
- `publishes_received` (int): Total PUBLISH packets received
- `publishes_sent` (int): Total PUBLISH packets sent
- `bytes_received` (int): Total bytes received
- `bytes_sent` (int): Total bytes sent
- `connections_total` (int): Total connection attempts
- `subscriptions` (int): Active subscription count
- `retained_messages` (int): Retained message count

#### get_subscriptions()

```python
def get_subscriptions(client_id=None)
```

Get active subscriptions.

**Parameters:**
- `client_id` (str or None): If provided, returns subscriptions for that client only.

**Returns:**
- If `client_id` is None: Dict mapping `{client_id: {topic_filter: granted_qos, ...}, ...}`
- If `client_id` is provided: Dict mapping `{topic_filter: granted_qos, ...}` for that client

#### get_retained_messages()

```python
def get_retained_messages()
```

Get all retained messages.

**Returns:** List of `(topic_str, payload_bytes, qos)` tuples.

#### clear_retained()

```python
def clear_retained(topic=None)
```

Clear retained messages.

**Parameters:**
- `topic` (str or bytes): Specific topic to clear, or None to clear all retained messages.

### Event Decorators

#### @on_connect

```python
@broker.on_connect
def handler(client_id, username, will_topic):
    pass  # return False to reject with CONNACK 0x05
```

Decorator for client connect event. Called BEFORE CONNACK is sent. Return `False` to reject the connection with CONNACK 0x05 (Not Authorized).

**Parameters:**
- `client_id` (str): Connected client identifier
- `username` (str or None): Username provided in CONNECT packet
- `will_topic` (str or None): Will topic if set, otherwise None

#### @on_publish

```python
@broker.on_publish
def handler(client_id, topic, payload, qos, retain):
    pass
```

Decorator for publish event. Called when a client publishes a message.

**Parameters:**
- `client_id` (str): Publishing client ID
- `topic` (bytes): Topic name
- `payload` (bytes): Message payload
- `qos` (int): QoS level (0, 1, or 2)
- `retain` (bool): Retain flag

#### @on_subscribe

```python
@broker.on_subscribe
def handler(client_id, topic_filter, requested_qos):
    return requested_qos  # or 0x80 to reject
```

Decorator for subscribe event. Can modify granted QoS or reject subscription.

**Parameters:**
- `client_id` (str): Subscribing client ID
- `topic_filter` (bytes): Topic filter (may contain wildcards)
- `requested_qos` (int): Requested QoS level

**Returns:** Granted QoS (0-2) or `0x80` to reject subscription.

#### @on_unsubscribe

```python
@broker.on_unsubscribe
def handler(client_id, topic_filter):
    pass
```

Decorator for unsubscribe event.

**Parameters:**
- `client_id` (str): Unsubscribing client ID
- `topic_filter` (bytes): Topic filter being unsubscribed

#### @on_disconnect

```python
@broker.on_disconnect
def handler(client_id, graceful):
    pass
```

Decorator for disconnect event.

**Parameters:**
- `client_id` (str): Disconnected client ID
- `graceful` (bool): True if client sent DISCONNECT, False if connection lost

#### @on_will_publish

```python
@broker.on_will_publish
def handler(client_id, topic, payload):
    return True  # return False to suppress will publication
```

Decorator for will publish event. Called when a client disconnects ungracefully and has a will message set. Return `False` to suppress the will message.

**Parameters:**
- `client_id` (str): Disconnected client ID
- `topic` (bytes): Will topic
- `payload` (bytes): Will payload

**Returns:** `True` to publish will (default), `False` to suppress.

#### @interceptor

```python
@broker.interceptor
def filter_func(ctx):
    if b'secret' in ctx.topic:
        ctx.drop()
```

Register a message interceptor. Interceptors are called in registration order before routing. Each receives a `MessageContext` and can modify it or call `ctx.drop()` to prevent delivery. Interceptors can also modify `ctx.topic`, `ctx.payload`, `ctx.qos`, and `ctx.retain` to alter the message before routing.

**Parameters:**
- `ctx` (MessageContext): Message context object

---

## BeehiveBrokerSimple

Simplified MQTT broker interface for quick setup.

### Constructor

```python
BeehiveBrokerSimple(port=1883, max_clients=10, users=None,
                    on_message=None, on_connect=None, on_disconnect=None,
                    auth=None, log_level='INFO')
```

**Parameters:**
- `port` (int): TCP port (default 1883)
- `max_clients` (int): Maximum concurrent clients (default 10)
- `users` (dict): Dict of `{username: password}` for authentication
- `on_message` (callable): Callback `(topic, payload, client_id)`
- `on_connect` (callable): Callback `(client_id)`
- `on_disconnect` (callable): Callback `(client_id)`
- `auth` (AuthProvider): Custom auth provider (overrides users)
- `log_level` (str): 'DEBUG', 'INFO', 'WARNING', 'ERROR'

**Example:**
```python
def handle_message(topic, payload, client_id):
    print("Message from %s: %s = %s" % (client_id, topic, payload))

broker = BeehiveBrokerSimple(
    port=1883,
    users={'alice': 'secret123'},
    on_message=handle_message
)
broker.run()
```

### Methods

#### run()

```python
def run()
```

Start broker (blocking). Handles KeyboardInterrupt gracefully.

#### serve_async()

```python
async def serve_async()
```

Start broker as async task (non-blocking).

#### publish()

```python
def publish(topic, payload, qos=0, retain=False)
```

Publish a message from broker itself. Creates a task and must be called from async context.

#### subscribe()

```python
def subscribe(topic_filter, callback)
```

Subscribe to messages matching a topic filter. Registers an internal hook that filters by topic.

**Parameters:**
- `topic_filter` (str): MQTT topic filter (supports +/# wildcards)
- `callback` (callable): Callback `(topic, payload, client_id)`

**Example:**
```python
broker = BeehiveBrokerSimple(port=1883)

def on_temp(topic, payload, client_id):
    print("Temperature: %s" % payload)

broker.subscribe('sensor/+/temp', on_temp)
broker.run()
```

---

## BrokerConfig

Configuration parameters for BeehiveMQTT broker.

### Constructor

```python
BrokerConfig(**kwargs)
```

All parameters are optional and have defaults. Override any parameter via keyword arguments.

**Example:**
```python
config = BrokerConfig(
    port=1883,
    max_clients=50,
    max_payload_size=8192,
    log_level='DEBUG'
)
```

### Network Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `bind_addr` | str | `'0.0.0.0'` | Interface address to bind to |
| `port` | int | `1883` | TCP port (1-65535) |
| `backlog` | int | `4` | TCP backlog queue size |

### Client Limits

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_clients` | int | `10` | Maximum concurrent clients |
| `max_subscriptions_per_client` | int | `20` | Max subscriptions per client |
| `max_topic_length` | int | `256` | Maximum topic name length in bytes |

### Message Size Limits

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_payload_size` | int | `4096` | Maximum message payload size in bytes |
| `max_packet_size` | int | `8192` | Maximum MQTT packet size in bytes |
| `max_queued_messages` | int | `50` | Max queued messages per offline session |

### QoS Settings

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `max_inflight` | int | `10` | Max in-flight QoS 1/2 messages per client |
| `max_retained_messages` | int | `100` | Max retained messages broker-wide |

### Timing Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connect_timeout` | int | `10` | Seconds to wait for CONNECT packet |
| `keep_alive_factor` | float | `1.5` | Multiplier for keep-alive timeout |
| `qos_retry_interval` | int | `10` | Seconds between QoS retransmission attempts |
| `qos_max_retries` | int | `3` | Max QoS retransmission attempts |
| `session_expiry` | int | `3600` | Offline session expiry in seconds |

### Feature Flags

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `allow_anonymous` | bool | `True` | Allow connections without credentials |
| `allow_zero_length_clientid` | bool | `True` | Allow empty client ID (auto-generate) |
| `retain_enabled` | bool | `True` | Enable retained message support |
| `qos2_enabled` | bool | `True` | Enable QoS 2 support |
| `sys_topics_enabled` | bool | `True` | Publish $SYS statistics topics |
| `stats_interval` | int | `60` | Seconds between $SYS topic updates |

### Performance Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `recv_buffer_size` | int | `1024` | Socket receive buffer size |
| `gc_collect_interval` | int | `30` | Seconds between garbage collection runs |
| `log_level` | str | `'INFO'` | Logging level: DEBUG, INFO, WARNING, ERROR |

### Methods

#### validate()

```python
def validate()
```

Validate configuration parameters. Raises `ValueError` if any parameter is invalid.

---

## MessageContext

Context passed to interceptors for each published message.

### Attributes

- `topic` (bytes): Topic name
- `payload` (bytes): Message payload
- `qos` (int): QoS level (0, 1, or 2)
- `retain` (bool): Retain flag
- `sender_id` (str): Client ID of publisher (or None for broker)

### Methods

#### drop()

```python
def drop()
```

Drop this message - it will not be routed to subscribers.

**Example:**
```python
@broker.interceptor
def block_profanity(ctx):
    if b'badword' in ctx.payload:
        ctx.drop()
```

---

## Authentication Classes

### AuthProvider

Base authentication provider - allows everything by default.

#### Methods

```python
def authenticate(client_id, username, password)
```
Returns `True` if authenticated. Default: `True`.

```python
def authorize_publish(client_id, topic)
```
Returns `True` if client can publish to topic. Default: `True`.

```python
def authorize_subscribe(client_id, topic_filter)
```
Returns max QoS (0-2) or -1 to deny. Default: `2`.

### DictAuthProvider

Simple dictionary-based authentication `{username: password}`.

#### Constructor

```python
DictAuthProvider(users)
```

**Parameters:**
- `users` (dict): Dict mapping `username -> password`

**Example:**
```python
auth = DictAuthProvider({
    'alice': 'secret123',
    'bob': 'password456'
})
```

### ACLAuthProvider

Role-based access control with topic patterns.

#### Constructor

```python
ACLAuthProvider()
```

#### Methods

```python
def add_user(username, password, role='default')
```
Add a user with password and role.

```python
def add_acl(role, topic_pattern, publish=True, subscribe=True)
```
Add ACL rule for role and topic pattern.

**Parameters:**
- `role` (str): User role name
- `topic_pattern` (str): MQTT topic pattern (supports +/# wildcards)
- `publish` (bool): Allow publish to matching topics
- `subscribe` (bool): Allow subscribe to matching topics

**Example:**
```python
acl = ACLAuthProvider()
acl.add_user('admin', 'admin123', role='admin')
acl.add_user('sensor1', 'pass', role='sensor')

acl.add_acl('admin', '#', publish=True, subscribe=True)
acl.add_acl('sensor', 'sensors/+/data', publish=True, subscribe=False)
acl.add_acl('sensor', 'sensors/+/command', publish=False, subscribe=True)
```

### CallbackAuthProvider

Delegates authentication and authorization decisions to user-provided callbacks.

#### Constructor

```python
CallbackAuthProvider(on_authenticate=None, on_authorize_publish=None,
                     on_authorize_subscribe=None)
```

**Parameters:**
- `on_authenticate` (callable): `(client_id, username, password) -> bool`
- `on_authorize_publish` (callable): `(client_id, topic) -> bool`
- `on_authorize_subscribe` (callable): `(client_id, topic_filter) -> int` (QoS or -1)

**Example:**
```python
def check_auth(client_id, username, password):
    return username == 'admin' and password == 'secret'

def check_publish(client_id, topic):
    return not topic.startswith(b'admin/')

auth = CallbackAuthProvider(
    on_authenticate=check_auth,
    on_authorize_publish=check_publish
)
```

---

## Topic and Routing

### TopicTree

Trie-based structure for efficient MQTT topic subscription and matching with wildcard support.

#### Methods

```python
def subscribe(topic_filter, client_id, qos)
```
Subscribe a client to a topic filter.

```python
def unsubscribe(topic_filter, client_id)
```
Unsubscribe a client from a topic filter. Returns `True` if found.

```python
def unsubscribe_all(client_id)
```
Remove all subscriptions for a client.

```python
def match(topic_name)
```
Find all subscribers matching a concrete topic name. Returns `{client_id: granted_qos}`.

```python
def set_retained(topic_name, payload, qos)
```
Set or clear a retained message for a topic. Empty payload clears.

```python
def get_retained(topic_name)
```
Get retained message for an exact topic. Returns `(topic_bytes, payload, qos)` or None.

```python
def get_retained_matching(topic_filter)
```
Get all retained messages matching a topic filter. Returns list of `(topic_bytes, payload, qos)`.

```python
def get_subscription_count()
```
Count total number of subscriptions across all topics.

```python
def get_retained_count()
```
Count number of retained messages in the tree.

### MessageRouter

Routes PUBLISH messages to matching subscribers.

**Note:** Typically used internally by MQTTBroker. Not intended for direct use.

---

## Error Classes

### MQTTError

Base exception for all MQTT-related errors.

**Attributes:**
- `message` (str): Error message

### MQTTProtocolError

Protocol violation error with optional MQTT reason code.

**Attributes:**
- `message` (str): Error message
- `reason_code` (int or None): MQTT reason code

### MQTTAuthError

Authentication or authorization failure.

### MQTTConnectionError

Connection-level error (network, timeout, disconnect).

### MQTTPayloadError

Payload too large, malformed, or invalid data.

**Example:**
```python
from beehivemqtt import MQTTProtocolError

try:
    # broker operations
    pass
except MQTTProtocolError as e:
    print("Protocol error: %s (code: %s)" % (e.message, e.reason_code))
```
