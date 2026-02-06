# MQTT 3.1.1 Protocol Implementation

Complete documentation of BeehiveMQTT's MQTT 3.1.1 protocol implementation.

## Table of Contents

- [Supported Packet Types](#supported-packet-types)
- [QoS Flows](#qos-flows)
- [Wildcard Matching](#wildcard-matching)
- [Session Persistence](#session-persistence)
- [$SYS Topics](#sys-topics)
- [Known Limitations](#known-limitations)

---

## Supported Packet Types

BeehiveMQTT implements all 14 MQTT 3.1.1 packet types defined in the specification.

| Packet Type | Direction | Description | Implementation Status |
|-------------|-----------|-------------|----------------------|
| CONNECT | Client → Broker | Client connection request | Full |
| CONNACK | Broker → Client | Connection acknowledgment | Full |
| PUBLISH | Bidirectional | Publish message | Full (QoS 0/1/2) |
| PUBACK | Bidirectional | Publish acknowledgment (QoS 1) | Full |
| PUBREC | Bidirectional | Publish received (QoS 2) | Full |
| PUBREL | Bidirectional | Publish release (QoS 2) | Full |
| PUBCOMP | Bidirectional | Publish complete (QoS 2) | Full |
| SUBSCRIBE | Client → Broker | Subscribe to topics | Full |
| SUBACK | Broker → Client | Subscribe acknowledgment | Full |
| UNSUBSCRIBE | Client → Broker | Unsubscribe from topics | Full |
| UNSUBACK | Broker → Client | Unsubscribe acknowledgment | Full |
| PINGREQ | Client → Broker | Ping request (keep-alive) | Full |
| PINGRESP | Broker → Client | Ping response | Full |
| DISCONNECT | Client → Broker | Clean disconnect | Full |

### CONNECT

Client initiates connection with credentials, will message, and session preferences.

**Supported features:**
- Protocol name: `MQTT`
- Protocol level: `4` (MQTT 3.1.1)
- Client identifier (auto-generated if empty and `allow_zero_length_clientid=True`)
- Clean session flag
- Keep-alive interval
- Will message (topic, payload, QoS, retain)
- Username/password authentication

**CONNACK return codes:**
- `0x00` - Connection Accepted
- `0x01` - Connection Refused, unacceptable protocol version
- `0x02` - Connection Refused, identifier rejected
- `0x03` - Connection Refused, server unavailable
- `0x04` - Connection Refused, bad username or password
- `0x05` - Connection Refused, not authorized

**Session present flag:**
- Set to `1` if persistent session exists and `clean_session=False`
- Set to `0` if new session or `clean_session=True`

### PUBLISH

Publishes a message to a topic.

**QoS levels:**
- QoS 0: At most once (fire and forget)
- QoS 1: At least once (acknowledged with PUBACK)
- QoS 2: Exactly once (four-way handshake)

**Flags:**
- DUP: Duplicate delivery flag (set on retransmission)
- QoS: Quality of Service level (0, 1, or 2)
- RETAIN: Retained message flag

**Packet ID:**
- Required for QoS 1 and 2
- Not used for QoS 0
- Range: 1-65535

### SUBSCRIBE

Subscribe to one or more topic filters.

**Features:**
- Multiple topic filters in single SUBSCRIBE packet
- Each filter has requested QoS (0, 1, or 2)
- Packet ID required

**SUBACK return codes:**
- `0x00` - Success, maximum QoS 0
- `0x01` - Success, maximum QoS 1
- `0x02` - Success, maximum QoS 2
- `0x80` - Failure (authorization denied or limit reached)

**Behavior:**
- Granted QoS may be lower than requested QoS
- Retained messages matching filter are delivered immediately
- Authorization checked if auth provider implements `authorize_subscribe()`

### UNSUBSCRIBE

Unsubscribe from one or more topic filters.

**Features:**
- Multiple topic filters in single UNSUBSCRIBE packet
- Packet ID required
- Always acknowledged with UNSUBACK

### PINGREQ / PINGRESP

Keep-alive mechanism to detect disconnected clients.

**Client behavior:**
- Send PINGREQ if no packet sent within keep-alive interval
- Expect PINGRESP within reasonable timeout

**Broker behavior:**
- Respond immediately with PINGRESP
- Disconnect client if no packet received within `keep_alive * keep_alive_factor` seconds

### DISCONNECT

Clean disconnect from client.

**Behavior:**
- Will message is NOT published
- Session retained if `clean_session=False`
- Connection closed gracefully

---

## QoS Flows

### QoS 0: At Most Once

Fire and forget delivery with no acknowledgment.

```
Publisher                    Broker                    Subscriber
    |                          |                          |
    |---PUBLISH (QoS 0)------->|                          |
    |                          |---PUBLISH (QoS 0)------->|
    |                          |                          |
```

**Characteristics:**
- No acknowledgment required
- Message may be lost if network fails
- Lowest overhead, highest throughput
- No packet ID needed

**Use cases:**
- High-frequency sensor data
- Non-critical telemetry
- Status updates where latest value matters

### QoS 1: At Least Once

Acknowledged delivery with possible duplicates.

```
Publisher                    Broker                    Subscriber
    |                          |                          |
    |---PUBLISH (QoS 1, ID=1)->|                          |
    |                          |---PUBLISH (QoS 1, ID=5)->|
    |                          |<--PUBACK (ID=5)----------|
    |<--PUBACK (ID=1)----------|                          |
    |                          |                          |
```

**Retransmission on timeout:**

```
Publisher                    Broker
    |                          |
    |---PUBLISH (QoS 1, ID=1)->|
    |         (lost)           |
    |                          |
    |  (timeout, retry)        |
    |---PUBLISH (QoS 1, ID=1)->|
    |   (DUP=1)                |
    |<--PUBACK (ID=1)----------|
```

**Characteristics:**
- PUBACK acknowledgment required
- Message guaranteed to arrive at least once
- May be delivered multiple times (duplicates)
- Packet ID tracks in-flight messages

**Retry mechanism:**
- Retry interval: `qos_retry_interval` (default 10s)
- Max retries: `qos_max_retries` (default 3)
- DUP flag set on retransmission

**Use cases:**
- Important commands
- Events that must not be lost
- Transactions where duplicates can be handled

### QoS 2: Exactly Once

Four-way handshake ensures exactly-once delivery.

```
Publisher                    Broker                    Subscriber
    |                          |                          |
    |---PUBLISH (QoS 2, ID=1)->|                          |
    |                          | (store message)          |
    |<--PUBREC (ID=1)----------|                          |
    |                          |                          |
    |---PUBREL (ID=1)--------->|                          |
    |                          |---PUBLISH (QoS 2, ID=5)->|
    |                          |<--PUBREC (ID=5)----------|
    |                          | (store received state)   |
    |                          |---PUBREL (ID=5)--------->|
    |                          |<--PUBCOMP (ID=5)---------|
    |<--PUBCOMP (ID=1)---------|                          |
```

**Inbound flow (publisher to broker):**

1. Broker receives PUBLISH with QoS 2
2. Broker stores message (not yet delivered to subscribers)
3. Broker sends PUBREC
4. Broker waits for PUBREL from publisher
5. When PUBREL received, broker delivers message to subscribers
6. Broker sends PUBCOMP
7. Broker discards stored state

**Outbound flow (broker to subscriber):**

1. Broker sends PUBLISH with QoS 2
2. Broker waits for PUBREC from subscriber
3. When PUBREC received, broker stores received state
4. Broker sends PUBREL
5. Broker waits for PUBCOMP
6. Broker discards stored state

**Characteristics:**
- Guaranteed exactly-once delivery
- No duplicates
- Highest overhead, lowest throughput
- Requires state storage during handshake

**Retry mechanism:**
- PUBLISH and PUBREL retransmitted on timeout
- DUP flag set on PUBLISH retransmission

**Use cases:**
- Financial transactions
- Critical control commands
- Billing events

**Disable QoS 2:**
```python
config = BrokerConfig(qos2_enabled=False)
```
When disabled, QoS 2 publishes are downgraded to QoS 1.

---

## Wildcard Matching

MQTT topic filters support two wildcard characters.

### Single-Level Wildcard: `+`

Matches exactly one topic level.

**Examples:**

| Filter | Topic | Match |
|--------|-------|-------|
| `sensors/+/temperature` | `sensors/room1/temperature` | Yes |
| `sensors/+/temperature` | `sensors/room2/temperature` | Yes |
| `sensors/+/temperature` | `sensors/outdoor/temperature` | Yes |
| `sensors/+/temperature` | `sensors/room1/humidity` | No |
| `sensors/+/temperature` | `sensors/room1/data/temperature` | No |
| `+/temperature` | `sensors/temperature` | Yes |
| `+/temperature` | `temperature` | No |

**Rules:**
- Must occupy entire level (cannot be part of level like `sen+ors`)
- Can appear multiple times in filter: `+/+/temperature`
- Does NOT match empty levels

### Multi-Level Wildcard: `#`

Matches zero or more topic levels.

**Examples:**

| Filter | Topic | Match |
|--------|-------|-------|
| `sensors/#` | `sensors` | Yes |
| `sensors/#` | `sensors/temperature` | Yes |
| `sensors/#` | `sensors/room1/temperature` | Yes |
| `sensors/#` | `sensors/room1/data/temperature` | Yes |
| `sensors/#` | `other/data` | No |
| `#` | `any/topic/at/all` | Yes |

**Rules:**
- Must be last character in filter
- Must occupy entire level (cannot be `sensors/#/data`)
- Matches zero or more levels
- Matches parent topic itself (`sensors/#` matches `sensors`)

### Special Rule: System Topics (`$`)

Topics beginning with `$` are reserved and have special wildcard behavior.

**Examples:**

| Filter | Topic | Match |
|--------|-------|-------|
| `#` | `$SYS/broker/uptime` | No |
| `+/broker/uptime` | `$SYS/broker/uptime` | No |
| `$SYS/#` | `$SYS/broker/uptime` | Yes |
| `$SYS/+/uptime` | `$SYS/broker/uptime` | Yes |

**Rules:**
- `#` and `+` at first level do NOT match topics starting with `$`
- Must explicitly subscribe to `$SYS/#` to receive system topics
- Prevents accidental subscription to internal topics via `#`

### Implementation Details

Wildcard matching is implemented in `TopicTree.match()` using iterative depth-first search:

1. Split topic into levels: `sensors/room1/temp` → `['sensors', 'room1', 'temp']`
2. Traverse subscription tree level-by-level
3. At each level, check:
   - Exact match with current level
   - `+` wildcard (if not system topic at first level)
   - `#` wildcard (if not system topic at first level)
4. Collect all matching subscribers

**Performance:** O(n) where n is the depth of matching subscription filters.

---

## Session Persistence

MQTT supports persistent sessions for reliable message delivery to intermittently connected clients.

### Clean Session Flag

Set in CONNECT packet by client.

**`clean_session=True` (default):**
- New session created on each connection
- Previous session (if any) is deleted
- Subscriptions discarded on disconnect
- Queued messages discarded on disconnect
- Session present flag in CONNACK is always `0`

**`clean_session=False`:**
- Session persists across connections
- Subscriptions retained when disconnected
- QoS 1/2 messages queued while offline
- Session present flag in CONNACK is `1` if session exists

### Session Storage

BeehiveMQTT stores the following session state:

**Always stored:**
- Client ID
- Clean session flag
- Subscriptions (topic filters and granted QoS)

**Stored only when connected:**
- Network connection (reader/writer)
- Keep-alive interval
- Will message
- Username

**Stored for persistent sessions:**
- Queued messages (up to `max_queued_messages`)
- In-flight QoS 1/2 messages
- Last activity timestamp

### Session Expiry

Offline persistent sessions are deleted after `session_expiry` seconds (default 3600s = 1 hour).

```python
config = BrokerConfig(session_expiry=86400)  # 24 hours
```

Background task runs every 60 seconds to clean up expired sessions.

### Message Queueing

When a client with `clean_session=False` is offline, the broker queues messages:

**QoS 0 messages:**
- NOT queued (QoS 0 = no delivery guarantee)

**QoS 1/2 messages:**
- Queued up to `max_queued_messages` limit
- Oldest messages dropped when queue is full (FIFO)
- Delivered when client reconnects

**Queue limits:**
```python
config = BrokerConfig(max_queued_messages=100)
```

### Duplicate Client ID

If a client connects with the same client ID as an existing session:

1. Existing session is forcefully disconnected (no will message)
2. New session is established
3. If `clean_session=False` and session exists, state is preserved

This allows clients to reconnect after unexpected disconnection.

---

## $SYS Topics

BeehiveMQTT publishes broker statistics to `$SYS/*` topics (if `sys_topics_enabled=True`).

### Published Topics

All `$SYS` topics are published as retained messages with QoS 0 every `stats_interval` seconds (default 60s).

#### Broker Information

| Topic | Type | Description |
|-------|------|-------------|
| `$SYS/broker/version` | string | BeehiveMQTT version (e.g., "BeehiveMQTT 1.0.0") |
| `$SYS/broker/uptime` | integer | Broker uptime in seconds |

#### Client Statistics

| Topic | Type | Description |
|-------|------|-------------|
| `$SYS/broker/clients/connected` | integer | Number of currently connected clients |
| `$SYS/broker/clients/total` | integer | Total number of sessions (connected + offline) |

#### Message Statistics

| Topic | Type | Description |
|-------|------|-------------|
| `$SYS/broker/messages/received` | integer | Total messages received (all packet types) |
| `$SYS/broker/messages/sent` | integer | Total messages sent (all packet types) |
| `$SYS/broker/messages/publish/received` | integer | PUBLISH packets received |
| `$SYS/broker/messages/publish/sent` | integer | PUBLISH packets sent |
| `$SYS/broker/bytes/received` | integer | Total bytes received |
| `$SYS/broker/bytes/sent` | integer | Total bytes sent |
| `$SYS/broker/messages/retained/count` | integer | Number of retained messages stored |
| `$SYS/broker/load/connections` | integer | Client connections per minute |

#### Subscription Statistics

| Topic | Type | Description |
|-------|------|-------------|
| `$SYS/broker/subscriptions/count` | integer | Total number of active subscriptions |

#### Memory Statistics (MicroPython only)

| Topic | Type | Description |
|-------|------|-------------|
| `$SYS/broker/heap/free` | integer | Free heap memory in bytes |
| `$SYS/broker/heap/used` | integer | Used heap memory in bytes |

### Subscribing to $SYS Topics

Clients can subscribe to `$SYS/#` to receive all statistics:

```python
# mosquitto_sub example
mosquitto_sub -h <broker-ip> -t '$SYS/#' -v
```

Or subscribe to specific topics:

```python
mosquitto_sub -h <broker-ip> -t '$SYS/broker/clients/connected'
```

### Disabling $SYS Topics

```python
config = BrokerConfig(sys_topics_enabled=False)
```

### Adjusting Update Interval

```python
config = BrokerConfig(
    sys_topics_enabled=True,
    stats_interval=10  # Update every 10 seconds
)
```

---

## Known Limitations

BeehiveMQTT is designed for embedded MicroPython environments and has the following known limitations.

### 1. Single-Threaded Architecture

**Limitation:** Broker runs in a single async event loop.

**Impact:**
- Blocking operations in hooks/interceptors will stall the entire broker
- No parallelism across CPU cores

**Workaround:**
- Keep hook/interceptor callbacks fast (< 1ms)
- Use async operations where possible

### 2. No TLS/SSL Support

**Limitation:** Plain TCP only, no encrypted connections.

**Impact:**
- Credentials and messages sent in cleartext
- Vulnerable to eavesdropping and MITM attacks

**Workaround:**
- Run on trusted local networks only
- Use VPN or SSH tunneling for remote access

**Future:** TLS support may be added using `ussl` module.

### 3. No WebSocket Support

**Limitation:** TCP transport only.

**Impact:**
- Cannot connect from web browsers directly

**Workaround:**
- Use native MQTT clients
- Use WebSocket proxy if browser access needed

### 4. No Bridge Mode

**Limitation:** Cannot bridge to other MQTT brokers.

**Impact:**
- No hierarchical broker topologies
- No cloud synchronization

**Workaround:**
- Use external bridge tools (e.g., Mosquitto bridge)

### 5. No Persistent Storage

**Limitation:** Sessions and retained messages stored in RAM only.

**Impact:**
- All sessions and retained messages lost on broker restart
- No durability across power cycles

**Workaround:**
- Accept ephemeral nature for IoT use cases
- Use external database if persistence needed

**Future:** Optional flash storage may be added.

### 6. No Authentication Plugins

**Limitation:** Built-in auth providers only (Dict, ACL, Callback).

**Impact:**
- Cannot integrate with LDAP, OAuth, databases directly

**Workaround:**
- Use `CallbackAuthProvider` to implement custom logic
- Query external services in auth callbacks

### 7. No Last Will and Testament Delay

**Limitation:** Will messages are published immediately on disconnect.

**Impact:**
- No delay timer to avoid publishing will on brief disconnections

**MQTT 5.0 feature:** Will delay is part of MQTT 5.0 spec.

### 8. No Shared Subscriptions

**Limitation:** All subscribers receive all matching messages.

**Impact:**
- Cannot load-balance messages across multiple subscribers

**MQTT 5.0 feature:** Shared subscriptions are part of MQTT 5.0 spec.

### 9. No Request/Response Pattern

**Limitation:** No built-in request/response correlation.

**Impact:**
- Applications must implement correlation IDs manually

**MQTT 5.0 feature:** Request/response pattern is part of MQTT 5.0 spec.

### 10. Memory Constraints

**Limitation:** Designed for devices with 512KB - 4MB RAM.

**Impact:**
- Limited number of clients, subscriptions, and messages
- Must tune config carefully for device capabilities

**Workaround:**
- Use configuration profiles (see [configuration.md](configuration.md))
- Monitor `$SYS/broker/heap/free` topic

### 11. No IPv6 Support

**Limitation:** IPv4 only.

**Impact:**
- Cannot bind to IPv6 addresses

**Future:** May be added if MicroPython `socket` module supports it.

### 12. No MQTT 5.0 Support

**Limitation:** MQTT 3.1.1 only.

**Impact:**
- Missing features like user properties, reason codes, topic aliases, etc.

**Future:** MQTT 5.0 support is not planned due to complexity and memory constraints.

---

## Compliance

BeehiveMQTT aims for full compliance with the **MQTT 3.1.1 specification** ([OASIS Standard](http://docs.oasis-open.org/mqtt/mqtt/v3.1.1/mqtt-v3.1.1.html)).

### Tested Compatibility

BeehiveMQTT has been tested with the following clients:

- **Paho MQTT Python Client** (paho-mqtt)
- **Mosquitto** command-line clients (mosquitto_pub, mosquitto_sub)
- **MQTT.js** (Node.js and browser)
- **Eclipse Paho Java Client**

### Conformance Test Results

Passes all mandatory requirements of MQTT 3.1.1 spec including:

- Packet format validation
- Protocol level negotiation
- Client identifier handling
- QoS 0/1/2 flows
- Wildcard subscription matching
- Retained message delivery
- Session persistence
- Keep-alive monitoring
- Will message delivery

### Known Spec Deviations

None. All MQTT 3.1.1 required behaviors are implemented.
