"""
Advanced MQTT Broker Example
=============================

Full-featured MQTT broker demonstrating all BeehiveMQTT capabilities.

This example demonstrates:
- Custom BrokerConfig with tuned parameters
- ACLAuthProvider with complex role-based access
- All event hooks (@on_connect, @on_publish, etc.)
- Multiple interceptors in pipeline
- Periodic statistics logging
- Memory and performance monitoring
- $SYS topics for monitoring
- QoS 0/1/2 support
- Retained messages
- Session persistence

Hardware: ESP32 with 4MB+ PSRAM recommended
Memory: ~70KB RAM minimum

This is a production-ready configuration suitable for:
- Industrial IoT deployments
- Smart building automation
- Multi-tenant sensor networks
- Mission-critical telemetry
"""

from beehivemqtt import MQTTBroker, BrokerConfig, MessageContext
from beehivemqtt.auth import ACLAuthProvider

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

import gc


# === Configuration ===

# Create custom broker configuration
config = BrokerConfig(
    # Network
    bind_addr='0.0.0.0',
    port=1883,
    backlog=8,

    # Client limits
    max_clients=20,
    max_subscriptions_per_client=50,
    max_topic_length=512,

    # Message size limits
    max_payload_size=8192,
    max_packet_size=16384,
    max_queued_messages=100,

    # QoS settings
    max_inflight=20,
    max_retained_messages=200,
    qos_retry_interval=15,
    qos_max_retries=5,

    # Timeouts
    connect_timeout=15,
    keep_alive_factor=1.5,

    # Session management
    session_expiry=7200,  # 2 hours

    # Feature flags
    allow_anonymous=False,  # Require authentication
    allow_zero_length_clientid=True,
    retain_enabled=True,
    qos2_enabled=True,

    # System topics and monitoring
    sys_topics_enabled=True,
    stats_interval=30,  # Publish stats every 30 seconds

    # Performance tuning
    recv_buffer_size=2048,
    gc_collect_interval=20,  # GC every 20 seconds

    # Logging
    log_level='DEBUG'
)


# === Authentication & Authorization ===

# Create ACL provider with role-based access
auth = ACLAuthProvider()

# Admin users - full access
auth.add_user('admin', 'admin_2024', role='admin')
auth.add_user('system', 'system_secure', role='admin')

# Sensor devices - publish only to sensor/+/data
auth.add_user('temp_sensor_01', 'sensor_pass_01', role='sensor')
auth.add_user('temp_sensor_02', 'sensor_pass_02', role='sensor')
auth.add_user('pressure_sensor_01', 'sensor_pass_03', role='sensor')

# Controllers - publish to control/+/command
auth.add_user('hvac_controller', 'hvac_pass', role='controller')
auth.add_user('light_controller', 'light_pass', role='controller')

# Monitoring clients - subscribe only
auth.add_user('dashboard', 'dash_pass', role='monitor')
auth.add_user('logger', 'log_pass', role='monitor')

# Define ACL rules
# Admin: Full access to all topics
auth.add_acl('admin', '#', publish=True, subscribe=True)

# Sensors: Publish to sensor/+/data, subscribe to sensor/+/config
auth.add_acl('sensor', 'sensor/+/data', publish=True, subscribe=False)
auth.add_acl('sensor', 'sensor/+/config', publish=False, subscribe=True)

# Controllers: Publish to control/+/command, subscribe to control/+/status
auth.add_acl('controller', 'control/+/command', publish=True, subscribe=False)
auth.add_acl('controller', 'control/+/status', publish=False, subscribe=True)

# Monitors: Subscribe to everything except admin
auth.add_acl('monitor', 'sensor/#', publish=False, subscribe=True)
auth.add_acl('monitor', 'control/#', publish=False, subscribe=True)
auth.add_acl('monitor', '$SYS/#', publish=False, subscribe=True)


# === Create Broker ===

broker = MQTTBroker(config=config, auth=auth)


# === Event Hooks ===

@broker.on_connect
def handle_connect(client_id, username, will_topic):
    """Log client connections with role information."""
    # Get client info
    clients = broker.get_clients()
    client = next((c for c in clients if c['client_id'] == client_id), None)

    if client:
        username = client.get('username', 'unknown')
        print('[Broker] CONNECT: %s (user=%s)' % (client_id, username))
    else:
        print('[Broker] CONNECT: %s' % client_id)

    # Print connection stats
    stats = broker.get_stats()
    print('[Broker] Connected clients: %d/%d' % (
        stats['clients_connected'],
        config.max_clients
    ))


@broker.on_publish
def handle_publish(client_id, topic, payload, qos, retain):
    """Log all publishes with metadata."""
    topic_str = topic.decode('utf-8') if isinstance(topic, bytes) else topic
    payload_len = len(payload)

    # Truncate payload for logging
    if isinstance(payload, bytes):
        payload_preview = payload[:50]
        if len(payload) > 50:
            payload_preview = payload_preview + b'...'
    else:
        payload_preview = str(payload)[:50]

    print('[Broker] PUBLISH: %s -> %s [%d bytes, QoS=%d, retain=%s]' % (
        client_id, topic_str, payload_len, qos, retain
    ))


@broker.on_subscribe
def handle_subscribe(client_id, topic_filter, requested_qos):
    """Log subscriptions and optionally modify granted QoS."""
    topic_str = topic_filter.decode('utf-8') if isinstance(topic_filter, bytes) else topic_filter
    print('[Broker] SUBSCRIBE: %s -> %s (QoS=%d)' % (
        client_id, topic_str, requested_qos
    ))

    # Grant requested QoS (or could downgrade here)
    return requested_qos


@broker.on_unsubscribe
def handle_unsubscribe(client_id, topic_filter):
    """Log unsubscribes."""
    topic_str = topic_filter.decode('utf-8') if isinstance(topic_filter, bytes) else topic_filter
    print('[Broker] UNSUBSCRIBE: %s -> %s' % (client_id, topic_str))


@broker.on_disconnect
def handle_disconnect(client_id, graceful):
    """Log disconnections."""
    status = 'CLEAN' if graceful else 'UNEXPECTED'
    print('[Broker] DISCONNECT: %s (%s)' % (client_id, status))


# === Interceptors ===

@broker.interceptor
def log_high_qos(ctx):
    """Log QoS 2 messages for debugging."""
    if ctx.qos == 2:
        topic_str = ctx.topic.decode('utf-8') if isinstance(ctx.topic, bytes) else ctx.topic
        print('[Interceptor] QoS2 message: %s from %s' % (topic_str, ctx.sender_id))


@broker.interceptor
def block_test_spam(ctx):
    """Block messages to test/spam topics."""
    topic_str = ctx.topic.decode('utf-8') if isinstance(ctx.topic, bytes) else ctx.topic

    if 'spam' in topic_str.lower() or topic_str.startswith('test/spam'):
        print('[Interceptor] Blocked spam message from %s' % ctx.sender_id)
        ctx.drop()


@broker.interceptor
def validate_sensor_format(ctx):
    """Validate sensor data format."""
    topic_str = ctx.topic.decode('utf-8') if isinstance(ctx.topic, bytes) else ctx.topic

    # Only validate sensor topics
    if not topic_str.startswith('sensor/'):
        return

    # Check if payload is valid (basic check)
    if len(ctx.payload) == 0:
        print('[Interceptor] Rejected empty sensor payload from %s' % ctx.sender_id)
        ctx.drop()


# === Background Tasks ===

async def stats_logger():
    """Periodically log detailed broker statistics."""
    while True:
        await asyncio.sleep(60)  # Every minute

        # Get statistics
        stats = broker.get_stats()

        # Get memory info if available
        try:
            mem_free = gc.mem_free()
            mem_alloc = gc.mem_alloc()
            mem_total = mem_free + mem_alloc
            mem_percent = (mem_alloc * 100) // mem_total
        except:
            mem_free = 0
            mem_alloc = 0
            mem_percent = 0

        print('[Stats] ==========================================')
        print('[Stats] Uptime: %d seconds' % stats['uptime'])
        print('[Stats] Clients: %d connected, %d total sessions' % (
            stats['clients_connected'],
            stats['clients_total']
        ))
        print('[Stats] Messages: RX=%d, TX=%d' % (
            stats['messages_received'],
            stats['messages_sent']
        ))
        print('[Stats] Publishes: RX=%d, TX=%d' % (
            stats['publishes_received'],
            stats['publishes_sent']
        ))
        print('[Stats] Bytes: RX=%d, TX=%d' % (
            stats['bytes_received'],
            stats['bytes_sent']
        ))
        print('[Stats] Subscriptions: %d active' % stats['subscriptions'])
        print('[Stats] Retained: %d messages' % stats['retained_messages'])

        if mem_percent > 0:
            print('[Stats] Memory: %d%% used (%d / %d bytes)' % (
                mem_percent, mem_alloc, mem_total
            ))

        print('[Stats] ==========================================')


async def health_monitor():
    """Monitor broker health and log warnings."""
    while True:
        await asyncio.sleep(30)

        stats = broker.get_stats()

        # Check if approaching client limit
        if stats['clients_connected'] >= config.max_clients * 0.8:
            print('[Health] WARNING: Approaching max clients (%d/%d)' % (
                stats['clients_connected'],
                config.max_clients
            ))

        # Check memory if available
        try:
            mem_free = gc.mem_free()
            if mem_free < 10000:  # Less than 10KB free
                print('[Health] WARNING: Low memory (free=%d bytes)' % mem_free)
        except:
            pass


# === Main Application ===

async def main():
    """Run the advanced broker with all features."""
    print('=' * 60)
    print('BeehiveMQTT Advanced Broker')
    print('=' * 60)
    print('Configuration:')
    print('  Port: %d' % config.port)
    print('  Max clients: %d' % config.max_clients)
    print('  Max payload: %d bytes' % config.max_payload_size)
    print('  QoS 2: %s' % ('ENABLED' if config.qos2_enabled else 'DISABLED'))
    print('  Retain: %s' % ('ENABLED' if config.retain_enabled else 'DISABLED'))
    print('  $SYS topics: %s' % ('ENABLED' if config.sys_topics_enabled else 'DISABLED'))
    print('  Authentication: REQUIRED')
    print('  ACL roles: admin, sensor, controller, monitor')
    print('=' * 60)
    print('Press Ctrl+C to stop')
    print('')

    # Start broker
    broker_task = asyncio.create_task(broker.serve())

    # Start monitoring tasks
    stats_task = asyncio.create_task(stats_logger())
    health_task = asyncio.create_task(health_monitor())

    # Run all tasks
    await asyncio.gather(broker_task, stats_task, health_task)


# === Run ===

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print('')
        print('[Broker] Shutting down gracefully...')

        # Print final stats
        stats = broker.get_stats()
        print('[Broker] Final statistics:')
        print('  Total runtime: %d seconds' % stats['uptime'])
        print('  Total connections: %d' % stats['connections_total'])
        print('  Messages received: %d' % stats['messages_received'])
        print('  Messages sent: %d' % stats['messages_sent'])
        print('[Broker] Goodbye!')
