# Configuration Guide

Complete reference for all BrokerConfig parameters in BeehiveMQTT.

## Quick Start

```python
from beehivemqtt import BrokerConfig, MQTTBroker

# Use defaults
config = BrokerConfig()

# Or customize parameters
config = BrokerConfig(
    port=1883,
    max_clients=50,
    log_level='DEBUG'
)

broker = MQTTBroker(config=config)
```

All parameters are optional. Override only what you need.

---

## Network Settings

### bind_addr

```python
bind_addr: str = '0.0.0.0'
```

Network interface address to bind the MQTT server to.

**Values:**
- `'0.0.0.0'` - Listen on all interfaces (default)
- `'127.0.0.1'` - Localhost only
- Specific IP address - Bind to single interface

**Example:**
```python
# Only accept local connections
config = BrokerConfig(bind_addr='127.0.0.1')
```

### port

```python
port: int = 1883
```

TCP port for MQTT connections.

**Range:** 1-65535

**Common values:**
- `1883` - Standard MQTT port (default)
- `8883` - MQTT over TLS (not yet supported)

**Validation:** Raises `ValueError` if not in range 1-65535.

**Example:**
```python
# Use non-standard port
config = BrokerConfig(port=8883)
```

### backlog

```python
backlog: int = 4
```

TCP listen backlog queue size. Controls how many pending connection requests can be queued while waiting for the broker to accept them.

**Range:** >= 1

**Default:** 4 (sufficient for most embedded use cases)

**When to adjust:**
- Increase if you see connection failures under burst load
- Keep low on memory-constrained devices

**Validation:** Raises `ValueError` if < 1.

---

## Client Limits

### max_clients

```python
max_clients: int = 10
```

Maximum number of concurrent client connections.

**Range:** >= 1

**Default:** 10

**Memory impact:** Each client session consumes approximately 500-1000 bytes. On ESP32 with 4MB PSRAM, 50-100 clients is feasible. On ESP32 without PSRAM (520KB RAM), stay under 20 clients.

**Behavior:** When limit is reached, new connections are immediately closed without CONNACK.

**Validation:** Raises `ValueError` if < 1.

**Example:**
```python
# High-memory device
config = BrokerConfig(max_clients=100)

# Memory-constrained device
config = BrokerConfig(max_clients=5)
```

### max_subscriptions_per_client

```python
max_subscriptions_per_client: int = 20
```

Maximum number of topic filter subscriptions per client.

**Range:** >= 0

**Default:** 20

**Memory impact:** Each subscription stores topic filter string plus client reference (approximately 40-100 bytes per subscription).

**Behavior:** When limit is reached, additional SUBSCRIBE requests return failure code `0x80` in SUBACK.

**Example:**
```python
# IoT device with simple subscriptions
config = BrokerConfig(max_subscriptions_per_client=5)

# Dashboard client with many topics
config = BrokerConfig(max_subscriptions_per_client=100)
```

### max_topic_levels

```python
max_topic_levels: int = 8
```

Maximum number of levels (segments separated by `/`) in a topic name.

**Range:** >= 1

**Default:** 8

**MQTT spec:** Topic names have no inherent level limit, but restricting depth prevents abuse.

**Behavior:** Topics with more levels than this limit are rejected during PUBLISH or SUBSCRIBE.

**Example:**
```python
# Allow deeper topic hierarchies
config = BrokerConfig(max_topic_levels=16)
```

### max_topic_length

```python
max_topic_length: int = 256
```

Maximum topic name or filter length in bytes.

**Range:** >= 1

**Default:** 256 bytes

**MQTT spec:** Topic names are limited to 65535 bytes, but practical limits are much lower.

**Behavior:** Topics exceeding this length are rejected during PUBLISH or SUBSCRIBE.

**Example:**
```python
# Embedded device with short topics
config = BrokerConfig(max_topic_length=128)
```

---

## Message Size Limits

### max_payload_size

```python
max_payload_size: int = 4096
```

Maximum message payload size in bytes.

**Range:** >= 1

**Default:** 4096 bytes (4 KB)

**Memory impact:** Payload bytes are allocated during message processing and routing.

**Behavior:** PUBLISH packets with payloads exceeding this size are silently dropped (logged as warning).

**Validation:** Raises `ValueError` if < 1.

**Example:**
```python
# Small sensor data
config = BrokerConfig(max_payload_size=512)

# Image thumbnails or JSON documents
config = BrokerConfig(max_payload_size=16384)  # 16 KB
```

### max_packet_size

```python
max_packet_size: int = 8192
```

Maximum MQTT packet size in bytes (includes header, topic, and payload).

**Range:** >= 1

**Default:** 8192 bytes (8 KB)

**MQTT packet structure:** Fixed header (2-5 bytes) + variable header + payload

**Behavior:** Packets exceeding this size cause the connection to be dropped.

**Guideline:** Set to at least `max_payload_size + max_topic_length + 64`.

**Example:**
```python
config = BrokerConfig(
    max_payload_size=4096,
    max_packet_size=8192
)
```

### max_queued_messages

```python
max_queued_messages: int = 50
```

Maximum number of messages queued for offline clients with persistent sessions (`clean_session=False`).

**Range:** >= 0

**Default:** 50 messages

**Memory impact:** Each queued message stores topic, payload, and QoS (~100-5000 bytes depending on payload).

**Behavior:** When queue is full, oldest messages are dropped (FIFO).

**Use case:** Allows offline clients to receive messages published while disconnected.

**Example:**
```python
# No offline queueing
config = BrokerConfig(max_queued_messages=0)

# Large queue for important data
config = BrokerConfig(max_queued_messages=200)
```

---

## QoS Settings

### max_inflight

```python
max_inflight: int = 10
```

Maximum number of in-flight QoS 1/2 messages per client.

**Range:** >= 0

**Default:** 10

**MQTT spec:** In-flight messages are those sent but not yet acknowledged.

**Memory impact:** Each in-flight message tracks packet ID, topic, payload, and retry state.

**Behavior:** When limit is reached, additional messages are queued until acknowledgments are received.

**Example:**
```python
# Low latency, few retries
config = BrokerConfig(max_inflight=5)

# High throughput with potential packet loss
config = BrokerConfig(max_inflight=20)
```

### max_retained_messages

```python
max_retained_messages: int = 100
```

Maximum number of retained messages broker-wide.

**Range:** >= 0

**Default:** 100

**Memory impact:** Each retained message stores topic, payload, and QoS.

**Behavior:** When limit is reached, the oldest retained message is evicted (LRU) to make room for the new one.

**Use case:** Status topics, configuration data, last known values.

**Example:**
```python
# Minimal retained storage
config = BrokerConfig(max_retained_messages=20)

# Large retained message store
config = BrokerConfig(max_retained_messages=500)
```

---

## Timing Parameters

### connect_timeout

```python
connect_timeout: int = 10
```

Seconds to wait for CONNECT packet after TCP connection is established.

**Range:** > 0

**Default:** 10 seconds

**Behavior:** If CONNECT is not received within this timeout, the connection is closed.

**Use case:** Prevents resource exhaustion from clients that connect but never send CONNECT.

**Example:**
```python
# Fast timeout for local network
config = BrokerConfig(connect_timeout=5)

# Tolerant for slow networks
config = BrokerConfig(connect_timeout=30)
```

### keep_alive_factor

```python
keep_alive_factor: float = 1.5
```

Multiplier for client keep-alive timeout.

**Range:** >= 1.0

**Default:** 1.5

**MQTT spec:** Clients send PINGREQ at keep-alive interval. Broker should wait 1.5x the interval before considering the client dead.

**Calculation:** `timeout = client_keep_alive * keep_alive_factor`

**Behavior:** If no packet is received within the calculated timeout, the client is disconnected.

**Example:**
```python
# Strict timeout
config = BrokerConfig(keep_alive_factor=1.2)

# Lenient for unreliable networks
config = BrokerConfig(keep_alive_factor=2.0)
```

### qos_retry_interval

```python
qos_retry_interval: int = 10
```

Seconds between QoS 1/2 message retransmission attempts.

**Range:** > 0

**Default:** 10 seconds

**MQTT spec:** If PUBACK (QoS 1) or PUBREC (QoS 2) is not received, the message is retransmitted with DUP flag set.

**Behavior:** Background task checks for unacknowledged messages every `qos_retry_interval` seconds.

**Example:**
```python
# Fast retries for low-latency network
config = BrokerConfig(qos_retry_interval=5)

# Slow retries for high-latency network
config = BrokerConfig(qos_retry_interval=30)
```

### qos_max_retries

```python
qos_max_retries: int = 3
```

Maximum number of QoS 1/2 retransmission attempts.

**Range:** >= 0

**Default:** 3 retries

**Behavior:** After `qos_max_retries` attempts, the message is dropped and logged as failed.

**Total time:** `qos_retry_interval * qos_max_retries` (default: 30 seconds)

**Example:**
```python
# Give up quickly
config = BrokerConfig(qos_max_retries=1)

# Persistent retries
config = BrokerConfig(qos_max_retries=10)
```

### no_keepalive_timeout

```python
no_keepalive_timeout: int = 3600
```

Timeout for clients that connect with `keep_alive=0` (no keepalive).

**Range:** >= 1

**Default:** 3600 seconds (1 hour)

**MQTT spec:** Clients with `keep_alive=0` have no keepalive obligation. The broker uses this timeout to disconnect truly idle clients.

**Behavior:** If no packet is received within this timeout from a client with `keep_alive=0`, the client is disconnected.

**Example:**
```python
# Short timeout for no-keepalive clients
config = BrokerConfig(no_keepalive_timeout=600)  # 10 minutes
```

### session_expiry

```python
session_expiry: int = 3600
```

Offline session expiry time in seconds.

**Range:** >= 0

**Default:** 3600 seconds (1 hour)

**Behavior:** Persistent sessions (`clean_session=False`) that remain disconnected longer than this value are deleted by the background cleanup task.

**Memory impact:** Persistent sessions retain subscriptions and queued messages even when offline.

**Example:**
```python
# Short-lived sessions
config = BrokerConfig(session_expiry=300)  # 5 minutes

# Long-lived sessions
config = BrokerConfig(session_expiry=86400)  # 24 hours
```

---

## Feature Flags

### allow_anonymous

```python
allow_anonymous: bool = True
```

Allow connections without username/password credentials.

**Default:** `True`

**Behavior:**
- `True`: Clients can connect without credentials (unless auth provider rejects)
- `False`: Clients without username are rejected with CONNACK code `0x05` (Not Authorized)

**Security:** Set to `False` in production environments with authentication enabled.

**Example:**
```python
# Require authentication
config = BrokerConfig(allow_anonymous=False)
```

### allow_zero_length_clientid

```python
allow_zero_length_clientid: bool = True
```

Allow clients to connect with empty client ID (auto-generate ID).

**Default:** `True`

**MQTT spec:** Clients with empty client ID must set `clean_session=True`.

**Behavior:**
- `True`: Empty client IDs are auto-generated
- `False`: Empty client IDs are rejected with CONNACK code `0x02` (Identifier Rejected)

**Example:**
```python
# Require explicit client IDs
config = BrokerConfig(allow_zero_length_clientid=False)
```

### retain_enabled

```python
retain_enabled: bool = True
```

Enable retained message support.

**Default:** `True`

**Behavior:**
- `True`: PUBLISH with retain flag stores message, delivered to new subscribers
- `False`: Retain flag is ignored, no retained messages stored or delivered

**Memory impact:** Retained messages consume memory until cleared.

**Example:**
```python
# Disable retained messages
config = BrokerConfig(retain_enabled=False)
```

### qos2_enabled

```python
qos2_enabled: bool = True
```

Enable QoS 2 (Exactly Once) support.

**Default:** `True`

**Behavior:**
- `True`: QoS 2 messages follow PUBREC/PUBREL/PUBCOMP flow
- `False`: QoS 2 publish requests are downgraded to QoS 1

**Memory impact:** QoS 2 tracking requires additional state per message.

**Example:**
```python
# Disable QoS 2 to save memory
config = BrokerConfig(qos2_enabled=False)
```

### sys_topics_enabled

```python
sys_topics_enabled: bool = True
```

Publish `$SYS/*` statistics topics.

**Default:** `True`

**Behavior:**
- `True`: Background task publishes broker statistics to `$SYS/*` topics every `stats_interval` seconds
- `False`: No `$SYS` topics are published

**Topics published:**
- `$SYS/broker/version`
- `$SYS/broker/uptime`
- `$SYS/broker/clients/connected`
- `$SYS/broker/clients/total`
- `$SYS/broker/messages/received`
- `$SYS/broker/messages/sent`
- `$SYS/broker/messages/publish/received`
- `$SYS/broker/messages/publish/sent`
- `$SYS/broker/bytes/received`
- `$SYS/broker/bytes/sent`
- `$SYS/broker/subscriptions/count`
- `$SYS/broker/messages/retained/count`
- `$SYS/broker/load/connections` (connections per minute)
- `$SYS/broker/heap/free` (MicroPython only)
- `$SYS/broker/heap/used` (MicroPython only)

**Example:**
```python
# Disable $SYS topics
config = BrokerConfig(sys_topics_enabled=False)
```

### stats_interval

```python
stats_interval: int = 60
```

Seconds between `$SYS` topic updates.

**Range:** > 0

**Default:** 60 seconds

**Behavior:** Only used if `sys_topics_enabled=True`.

**Example:**
```python
# Update stats every 10 seconds
config = BrokerConfig(
    sys_topics_enabled=True,
    stats_interval=10
)
```

---

## Performance Parameters

### recv_buffer_size

```python
recv_buffer_size: int = 1024
```

Socket receive buffer size in bytes.

**Range:** > 0

**Default:** 1024 bytes

**Use case:** Affects TCP socket receive buffer allocation.

**When to adjust:**
- Increase for high-throughput scenarios
- Decrease on extremely memory-constrained devices

**Example:**
```python
# Minimal buffer
config = BrokerConfig(recv_buffer_size=512)

# Large buffer for throughput
config = BrokerConfig(recv_buffer_size=4096)
```

### gc_collect_interval

```python
gc_collect_interval: int = 30
```

Seconds between automatic garbage collection runs.

**Range:** > 0

**Default:** 30 seconds

**MicroPython specific:** Calls `gc.collect()` periodically to reclaim memory.

**Behavior:** Background task triggers garbage collection at this interval.

**When to adjust:**
- Decrease if experiencing memory fragmentation
- Increase if GC pauses are impacting performance

**Example:**
```python
# Aggressive GC
config = BrokerConfig(gc_collect_interval=10)

# Minimal GC overhead
config = BrokerConfig(gc_collect_interval=60)
```

### log_level

```python
log_level: str = 'INFO'
```

Logging verbosity level.

**Values:**
- `'DEBUG'` - Verbose logging, all events
- `'INFO'` - Normal logging, connections and important events (default)
- `'WARNING'` - Warnings and errors only
- `'ERROR'` - Errors only

**Performance:** DEBUG level logging can impact performance on high-traffic brokers.

**Example:**
```python
# Development
config = BrokerConfig(log_level='DEBUG')

# Production
config = BrokerConfig(log_level='WARNING')
```

---

## Validation

All configuration parameters are validated when the broker starts.

```python
config = BrokerConfig(port=99999)
config.validate()  # Raises ValueError: port must be in range 1-65535
```

Validation is automatically called by `MQTTBroker.__init__()`, so you typically don't need to call `validate()` manually.

---

## Common Configuration Profiles

### Minimal Memory (ESP32 without PSRAM)

```python
config = BrokerConfig(
    max_clients=5,
    max_subscriptions_per_client=10,
    max_payload_size=512,
    max_packet_size=1024,
    max_queued_messages=10,
    max_inflight=3,
    max_retained_messages=20,
    gc_collect_interval=20,
    log_level='WARNING'
)
```

### High Performance (ESP32 with PSRAM)

```python
config = BrokerConfig(
    max_clients=100,
    max_subscriptions_per_client=50,
    max_payload_size=8192,
    max_packet_size=16384,
    max_queued_messages=200,
    max_inflight=20,
    max_retained_messages=500,
    backlog=8,
    gc_collect_interval=60,
    log_level='INFO'
)
```

### Secure Production

```python
config = BrokerConfig(
    allow_anonymous=False,
    allow_zero_length_clientid=False,
    max_clients=50,
    connect_timeout=5,
    keep_alive_factor=1.2,
    log_level='WARNING'
)
```

### Local Testing

```python
config = BrokerConfig(
    bind_addr='127.0.0.1',
    port=1883,
    max_clients=10,
    log_level='DEBUG',
    sys_topics_enabled=True,
    stats_interval=5
)
```
