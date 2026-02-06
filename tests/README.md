# BeehiveMQTT Test Suite

Comprehensive test suite for the BeehiveMQTT MQTT 3.1.1 broker.

## Structure

- `micropython_compat.py` - MicroPython compatibility shim for CPython testing
- `conftest.py` - pytest configuration and fixtures
- `test_utils.py` - Tests for utility functions (encoding, validation, etc.)
- `test_packet.py` - Tests for MQTT packet parsing and building
- `test_topic.py` - Tests for topic tree (subscriptions, wildcards, retained)
- `test_session.py` - Tests for client session management
- `test_qos.py` - Tests for QoS 1/2 state machines
- `test_router.py` - Tests for message routing
- `test_auth.py` - Tests for authentication and authorization
- `test_retained.py` - Tests for retained message store
- `test_stats.py` - Tests for broker statistics and memory guard
- `test_broker.py` - Tests for broker initialization and public methods
- `test_simple_api.py` - Tests for simplified broker API
- `test_hooks.py` - Tests for broker hooks and interceptors
- `test_compliance.py` - MQTT 3.1.1 specification compliance tests

## Running Tests

### Prerequisites

Install pytest and pytest-asyncio:

```bash
pip install pytest pytest-asyncio
```

### Run All Tests

```bash
cd BeehiveMQTT
pytest tests/
```

### Run Specific Test File

```bash
pytest tests/test_packet.py
```

### Run Specific Test

```bash
pytest tests/test_packet.py::TestConnackPacket::test_build_connack_accepted
```

### Run with Verbose Output

```bash
pytest tests/ -v
```

### Run with Coverage

```bash
pip install pytest-cov
pytest tests/ --cov=beehivemqtt --cov-report=html
```

## Test Coverage

The test suite covers:

- **Protocol Encoding/Decoding**: All MQTT 3.1.1 packet types
- **Topic Matching**: Exact, + wildcard, # wildcard, $SYS filtering
- **Session Management**: Clean/persistent sessions, keep-alive, packet IDs
- **QoS Flows**: QoS 0, 1, and 2 message delivery
- **Routing**: Message delivery, retained messages, offline queueing
- **Authentication**: Dict-based, ACL-based, callback-based auth
- **Broker Hooks**: on_connect, on_publish, on_subscribe, etc.
- **Interceptors**: Message modification and filtering
- **MQTT 3.1.1 Compliance**: Key specification requirements

## Compatibility

All tests run on CPython using the `micropython_compat` shim which patches:
- `time.ticks_ms()`, `time.ticks_diff()`, `time.ticks_cpu()`
- `gc.mem_free()`, `gc.mem_alloc()`

This allows testing the MicroPython-targeted code on a standard Python installation.

## Mock Objects

The test suite uses mock StreamReader/StreamWriter objects defined in `conftest.py`:
- `MockWriter` - Captures written data for assertions
- `MockReader` - Provides test data to read operations

These mocks simulate asyncio stream operations without requiring network connections.
