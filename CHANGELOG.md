# Changelog

All notable changes to BeehiveMQTT will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [1.0.0] - 2024-01-01

### Added

- Full MQTT 3.1.1 protocol support (all 14 packet types)
- QoS 0, 1, and 2 message delivery
- Topic wildcards: single-level (+) and multi-level (#)
- Retained message storage with configurable limits
- Will messages (Last Will and Testament)
- Persistent sessions with offline message queueing
- Pluggable authentication: DictAuthProvider, ACLAuthProvider, CallbackAuthProvider
- Role-based access control with topic pattern matching
- $SYS monitoring topics for broker statistics
- MemoryGuard for OOM protection on embedded devices
- Event hooks: on_connect, on_publish, on_subscribe, on_unsubscribe, on_disconnect
- Message interceptor pipeline with drop() support
- Management API: get_clients(), get_stats(), disconnect_client(), etc.
- BeehiveBrokerSimple for 3-line broker setup
- Configurable via BrokerConfig with 25+ parameters
- Background tasks: GC, keep-alive monitor, QoS retransmit, session cleanup
- Full CPython compatibility for development and testing
- MicroPython optimized: __slots__, iterative algorithms, struct-based parsing
