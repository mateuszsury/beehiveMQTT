"""
BeehiveMQTT Broker - Core MQTT 3.1.1 broker implementation.

Full-featured broker with QoS 0/1/2, authentication, logging,
statistics, and memory management.
"""

import gc
import struct
import time

try:
    import asyncio
except ImportError:
    import uasyncio as asyncio

from .config import BrokerConfig
from .errors import MQTTProtocolError, MQTTConnectionError
from .session import ClientSession, SessionManager
from .topic import TopicTree
from .router import MessageRouter
from .qos import QoSManager
from .retained import RetainedStore
from .logging import get_logger
from .stats import BrokerStats, MemoryGuard
from .utils import generate_client_id, validate_topic_name, validate_topic_filter
from . import packet


class MessageContext:
    """Context passed to interceptors for each published message."""
    __slots__ = ('topic', 'payload', 'qos', 'retain', 'sender_id', '_dropped')

    def __init__(self, topic, payload, qos, retain, sender_id):
        self.topic = topic
        self.payload = payload
        self.qos = qos
        self.retain = retain
        self.sender_id = sender_id
        self._dropped = False

    def drop(self):
        """Drop this message - it will not be routed."""
        self._dropped = True


class MQTTBroker:
    """
    Native MicroPython MQTT 3.1.1 broker.

    Handles client connections, authentication, pub/sub routing,
    session management, logging, statistics, and memory guarding.

    Example:
        broker = MQTTBroker(config=BrokerConfig(port=1883))

        @broker.on_connect
        def handle_connect(client_id):
            print("Client connected:", client_id)

        await broker.serve()
    """

    def __init__(self, config=None, auth=None):
        """
        Initialize the MQTT broker.

        Args:
            config: BrokerConfig instance. If None, uses defaults.
            auth: Authentication handler (None = allow all connections).
        """
        self.config = config or BrokerConfig()
        self.config.validate()

        # Logger
        self._log = get_logger('BeehiveMQTT', self.config.log_level)

        # Core data structures
        self.sessions = {}  # client_id (str) -> ClientSession
        self.topic_tree = TopicTree()
        self.qos_manager = QoSManager(self.config)
        self.retained_store = RetainedStore(self.topic_tree, self.config)

        # Statistics and memory guard
        self.stats = BrokerStats()
        self._memory_guard = MemoryGuard()

        # Router with retained_store and stats
        self.router = MessageRouter(
            self.topic_tree, self.sessions, self.config,
            self.qos_manager, self.retained_store, self.stats
        )
        self.session_manager = SessionManager(self.sessions, self.config)

        # Authentication
        self.auth = auth  # None means allow all

        # Server state
        self._server = None
        self._running = False
        self._tasks = []

        # Hook callbacks
        self._on_connect = None
        self._on_publish = None
        self._on_subscribe = None
        self._on_unsubscribe = None
        self._on_disconnect = None
        self._on_will_publish = None

        # Interceptor pipeline
        self._interceptors = []

    # Helper for firing hooks (sync + async compatible)

    async def _fire_hook(self, hook, *args):
        """Fire a hook callback, handling both sync and async functions.

        Args:
            hook: Callable (sync or async) or None
            *args: Arguments to pass to the hook

        Returns:
            Return value from the hook, or None if hook is None or errors
        """
        if hook is None:
            return None
        try:
            result = hook(*args)
            if hasattr(result, 'send'):  # coroutine check
                result = await result
            return result
        except Exception as e:
            self._log.error("Error in hook: %s", e)
            return None

    # Hook decorators

    def on_connect(self, func):
        """
        Decorator for client connect event.

        Called BEFORE CONNACK is sent. Return False to reject with CONNACK 0x05.

        @broker.on_connect
        def handler(client_id, username, will_topic):
            pass  # return False to reject
        """
        self._on_connect = func
        return func

    def on_publish(self, func):
        """
        Decorator for publish event.

        @broker.on_publish
        def handler(client_id, topic, payload, qos, retain):
            pass
        """
        self._on_publish = func
        return func

    def on_subscribe(self, func):
        """
        Decorator for subscribe event.

        @broker.on_subscribe
        def handler(client_id, topic_filter, requested_qos):
            return requested_qos  # or 0x80 to reject
        """
        self._on_subscribe = func
        return func

    def on_unsubscribe(self, func):
        """
        Decorator for unsubscribe event.

        @broker.on_unsubscribe
        def handler(client_id, topic_filter):
            pass
        """
        self._on_unsubscribe = func
        return func

    def on_disconnect(self, func):
        """
        Decorator for disconnect event.

        @broker.on_disconnect
        def handler(client_id, graceful):
            pass
        """
        self._on_disconnect = func
        return func

    def on_will_publish(self, func):
        """
        Decorator for will publish event.

        @broker.on_will_publish
        def handler(client_id, topic, payload):
            return True  # return False to suppress will publication
        """
        self._on_will_publish = func
        return func

    def interceptor(self, func):
        """
        Register a message interceptor.

        Interceptors are called in order before routing. Each receives
        a MessageContext and can modify it or call ctx.drop() to prevent
        delivery.

        @broker.interceptor
        def my_filter(ctx):
            if b'secret' in ctx.topic:
                ctx.drop()
        """
        self._interceptors.append(func)
        return func

    # Main server

    async def serve(self):
        """
        Start the MQTT broker server.

        This is the main entry point. Starts the TCP server and background tasks.
        Runs until shutdown() is called.
        """
        self._running = True

        try:
            # Start TCP server
            self._server = await asyncio.start_server(
                self._handle_client,
                self.config.bind_addr,
                self.config.port
            )

            self._log.info("Broker started on %s:%d", self.config.bind_addr, self.config.port)

            # Start background tasks
            gc_task = asyncio.create_task(self._gc_task())
            ka_task = asyncio.create_task(self._keep_alive_monitor())
            retransmit_task = asyncio.create_task(self._retransmit_task())
            session_cleanup_task = asyncio.create_task(self._session_cleanup_task())
            self._tasks.extend([gc_task, ka_task, retransmit_task, session_cleanup_task])

            # Start $SYS topics task if enabled
            if self.config.sys_topics_enabled:
                sys_task = asyncio.create_task(self._sys_topics_task())
                self._tasks.append(sys_task)

            # Wait forever (until shutdown)
            while self._running:
                await asyncio.sleep(1)

        finally:
            await self.shutdown()

    async def _read_with_timeout(self, reader, timeout):
        """
        Read a packet with timeout. Works on both MicroPython and CPython.

        Args:
            reader: StreamReader
            timeout: Timeout in seconds

        Returns:
            Tuple of (packet_type, flags, payload_bytes)
        """
        try:
            return await asyncio.wait_for(packet.read_packet(reader), timeout)
        except AttributeError:
            return await packet.read_packet(reader)

    async def _handle_client(self, reader, writer):
        """
        Handle a single client connection.

        Args:
            reader: StreamReader
            writer: StreamWriter
        """
        session = None

        try:
            # Memory guard check before accepting
            mem_status = self._memory_guard.check()
            if mem_status == MemoryGuard.CRITICAL:
                self._log.warning("Memory CRITICAL, rejecting connection")
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return
            elif mem_status == MemoryGuard.LOW:
                self._log.warning("Memory LOW, trimming queues")
                self._memory_guard.trim_queues(self.sessions)

            # Check max clients limit
            if len(self.sessions) >= self.config.max_clients:
                self._log.warning("Max clients reached, rejecting connection")
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return

            # Track connection attempt
            self.stats.record_connection()

            # Read CONNECT packet with timeout
            try:
                packet_type, flags, data = await self._read_with_timeout(
                    reader,
                    self.config.connect_timeout
                )
            except Exception as e:
                self._log.debug("Connection timeout or read error: %s", e)
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return

            # Track bytes received
            self.stats.messages_received += 1
            self.stats.bytes_received += len(data) if data else 0

            # First packet must be CONNECT
            if packet_type != packet.CONNECT:
                self._log.warning("First packet not CONNECT, closing")
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return

            # Check if broker is shutting down
            if not self._running:
                self._log.warning("Broker shutting down, rejecting connection")
                await self._send_connack(writer, False, 0x03)
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return

            # Parse CONNECT and authenticate
            connect_data = packet.parse_connect(data)
            session = await self._process_connect(connect_data, reader, writer)

            if session is None:
                return

            self._log.info("Client connected: %s", session.client_id)

            # Main message loop
            while session.connected and self._running:
                # Calculate timeout based on keep_alive
                if session.keep_alive > 0:
                    timeout = session.keep_alive * self.config.keep_alive_factor
                else:
                    timeout = self.config.no_keepalive_timeout

                try:
                    packet_type, flags, data = await self._read_with_timeout(
                        reader,
                        timeout
                    )
                except Exception as e:
                    self._log.debug("Read error for %s: %s", session.client_id, e)
                    break

                # Track stats
                self.stats.messages_received += 1
                self.stats.bytes_received += len(data) if data else 0

                # Update activity timestamp
                session.update_activity()

                # Dispatch based on packet type
                if packet_type == packet.PUBLISH:
                    await self._process_publish(session, data, flags)

                elif packet_type == packet.SUBSCRIBE:
                    await self._process_subscribe(session, data)

                elif packet_type == packet.UNSUBSCRIBE:
                    await self._process_unsubscribe(session, data)

                elif packet_type == packet.PINGREQ:
                    await session.send(packet.PINGRESP_BYTES)
                    self.stats.messages_sent += 1

                elif packet_type == packet.DISCONNECT:
                    await self._process_disconnect(session)
                    break

                elif packet_type == packet.CONNECT:
                    self._log.warning("Protocol error: second CONNECT from %s", session.client_id)
                    break

                elif packet_type == packet.PUBACK:
                    await self._process_puback(session, data)

                elif packet_type == packet.PUBREC:
                    await self._process_pubrec(session, data)

                elif packet_type == packet.PUBREL:
                    await self._process_pubrel(session, data)

                elif packet_type == packet.PUBCOMP:
                    await self._process_pubcomp(session, data)

                # Unknown packet types are ignored per MQTT spec

        except (OSError, MQTTProtocolError, MQTTConnectionError) as e:
            self._log.error("Connection error: %s", e)

        except Exception as e:
            self._log.error("Unexpected error: %s", e)

        finally:
            if session:
                await self._handle_disconnect(session, graceful=False)

    async def _process_connect(self, connect_data, reader, writer):
        """
        Process CONNECT packet and establish session.

        Args:
            connect_data: Parsed ConnectData
            reader: StreamReader
            writer: StreamWriter

        Returns:
            ClientSession if accepted, None if rejected
        """
        # Validate protocol
        if connect_data.protocol_name != b'MQTT' or connect_data.protocol_level != 4:
            await self._send_connack(writer, False, 0x01)
            writer.close()
            await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
            return None

        # Handle client_id
        client_id = connect_data.client_id

        if not client_id or len(client_id) == 0:
            if self.config.allow_zero_length_clientid and connect_data.clean_session:
                client_id = generate_client_id()
            elif not connect_data.clean_session:
                await self._send_connack(writer, False, 0x02)
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return None
            else:
                await self._send_connack(writer, False, 0x02)
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return None

        # Decode client_id to string
        if isinstance(client_id, bytes):
            try:
                client_id = client_id.decode('utf-8')
            except (UnicodeDecodeError, ValueError):
                await self._send_connack(writer, False, 0x02)
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return None

        # Authenticate
        if self.auth:
            username = connect_data.username.decode('utf-8') if connect_data.username else None
            password = connect_data.password.decode('utf-8') if connect_data.password else None

            if not self.auth.authenticate(client_id, username, password):
                self._log.warning("Auth failed for client %s (user=%s)", client_id, username)
                await self._send_connack(writer, False, 0x04)
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return None
        elif not self.config.allow_anonymous:
            # No auth provider but anonymous not allowed
            if not connect_data.has_username:
                self._log.warning("Anonymous connection rejected: %s", client_id)
                await self._send_connack(writer, False, 0x05)
                writer.close()
                await writer.wait_closed() if hasattr(writer, 'wait_closed') else None
                return None

        # Handle duplicate client_id (force disconnect old session)
        if client_id in self.sessions:
            old_session = self.sessions[client_id]
            if old_session.connected:
                self._log.info("Disconnecting duplicate client: %s", client_id)
                await self._handle_disconnect(old_session, graceful=False)

        # Create or retrieve session
        session_present = False

        if connect_data.clean_session:
            session = ClientSession(client_id, clean_session=True)
        else:
            if client_id in self.sessions:
                session = self.sessions[client_id]
                session_present = True
            else:
                session = ClientSession(client_id, clean_session=False)

        # Configure session
        session.reader = reader
        session.writer = writer
        session.connected = True
        session.keep_alive = connect_data.keep_alive
        session.update_activity()

        # Store will message
        if connect_data.has_will:
            session.will_topic = connect_data.will_topic
            session.will_message = connect_data.will_message
            session.will_qos = connect_data.will_qos
            session.will_retain = connect_data.will_retain

        # Store username
        if connect_data.has_username:
            session.username = connect_data.username.decode('utf-8') if isinstance(connect_data.username, bytes) else connect_data.username

        # Prepare hook arguments (username and will_topic as strings)
        username_str = session.username
        if connect_data.has_will and connect_data.will_topic:
            will_topic_str = connect_data.will_topic.decode('utf-8') if isinstance(connect_data.will_topic, bytes) else connect_data.will_topic
        else:
            will_topic_str = None

        # Store in sessions dict
        self.sessions[client_id] = session

        # Fire on_connect hook BEFORE sending CONNACK (per MQTT-3.3.5)
        result = await self._fire_hook(self._on_connect, client_id, username_str, will_topic_str)
        if result is False:
            self._log.info("on_connect rejected client: %s", client_id)
            await self._send_connack(writer, False, 0x05)
            session.will_topic = None
            session.will_message = None
            session.connected = False
            writer.close()
            if hasattr(writer, 'wait_closed'):
                await writer.wait_closed()
            if self.auth and hasattr(self.auth, 'cleanup_client'):
                self.auth.cleanup_client(client_id)
            if client_id in self.sessions:
                del self.sessions[client_id]
            return None

        # Send CONNACK
        await self._send_connack(writer, session_present, 0x00)
        self.stats.messages_sent += 1

        # Deliver queued messages if persistent session
        if session_present and not connect_data.clean_session:
            await self.router.deliver_queued(session)

        return session

    async def _send_connack(self, writer, session_present, return_code):
        """Send CONNACK packet."""
        connack = packet.build_connack(session_present, return_code)
        writer.write(connack)
        await writer.drain()

    async def _process_publish(self, session, data, flags):
        """
        Process PUBLISH packet.

        Args:
            session: ClientSession
            data: Raw packet payload
            flags: PUBLISH flags
        """
        try:
            publish = packet.parse_publish(data, flags)
        except Exception as e:
            self._log.warning("Error parsing PUBLISH: %s", e)
            return

        # Validate topic name
        try:
            validate_topic_name(publish.topic)
        except ValueError as e:
            self._log.warning("Invalid topic from %s: %s", session.client_id, e)
            return

        # Check topic levels
        if hasattr(self.config, 'max_topic_levels'):
            topic_str = publish.topic.decode('utf-8') if isinstance(publish.topic, bytes) else publish.topic
            if topic_str.count('/') + 1 > self.config.max_topic_levels:
                self._log.warning("Too many topic levels from %s", session.client_id)
                return

        # Check payload size
        if len(publish.payload) > self.config.max_payload_size:
            self._log.warning("Payload too large from %s: %d bytes", session.client_id, len(publish.payload))
            return

        # Check qos2_enabled
        if publish.qos == 2 and not self.config.qos2_enabled:
            self._log.warning("QoS 2 disabled, dropping PUBLISH from %s", session.client_id)
            # Per MQTT-3.3.5: MUST still send PUBREC for QoS 2
            await session.send(packet.build_pubrec(publish.packet_id))
            self.stats.messages_sent += 1
            return

        # Authorize publish
        if self.auth and hasattr(self.auth, 'authorize_publish'):
            if not self.auth.authorize_publish(session.client_id, publish.topic):
                self._log.warning("Publish denied for %s on %s", session.client_id, publish.topic)
                # Per MQTT-3.3.5: MUST send ACK even for unauthorized publish
                if publish.qos == 1:
                    await session.send(packet.build_puback(publish.packet_id))
                    self.stats.messages_sent += 1
                elif publish.qos == 2:
                    await session.send(packet.build_pubrec(publish.packet_id))
                    self.stats.messages_sent += 1
                return

        # Run interceptor pipeline
        if self._interceptors:
            ctx = MessageContext(publish.topic, publish.payload, publish.qos, publish.retain, session.client_id)
            for intercept in self._interceptors:
                try:
                    intercept_result = intercept(ctx)
                    if hasattr(intercept_result, 'send'):
                        await intercept_result
                except Exception as e:
                    self._log.error("Error in interceptor: %s", e)
                if ctx._dropped:
                    return
            # Allow interceptors to modify the message
            publish.topic = ctx.topic
            publish.payload = ctx.payload
            publish.qos = ctx.qos
            publish.retain = ctx.retain

        # Track stats
        self.stats.publishes_received += 1

        # Fire on_publish hook
        await self._fire_hook(
            self._on_publish,
            session.client_id,
            publish.topic,
            publish.payload,
            publish.qos,
            publish.retain
        )

        # Handle QoS flows
        if publish.qos == 0:
            await self.router.route_publish(
                publish.topic,
                publish.payload,
                publish.qos,
                publish.retain,
                session.client_id
            )
        elif publish.qos == 1:
            await self.router.route_publish(
                publish.topic,
                publish.payload,
                publish.qos,
                publish.retain,
                session.client_id
            )
            await session.send(packet.build_puback(publish.packet_id))
            self.stats.messages_sent += 1
        elif publish.qos == 2:
            self.qos_manager.track_inbound_qos2(session, publish.packet_id, publish.topic, publish.payload, publish.retain)
            await session.send(packet.build_pubrec(publish.packet_id))
            self.stats.messages_sent += 1

    async def _process_subscribe(self, session, data):
        """
        Process SUBSCRIBE packet.

        Args:
            session: ClientSession
            data: Raw packet payload
        """
        try:
            subscribe = packet.parse_subscribe(data)
        except Exception as e:
            self._log.warning("Error parsing SUBSCRIBE: %s", e)
            return

        granted_qos_list = []

        for topic_filter, requested_qos in subscribe.topics:
            # Check subscription limit
            if len(session.subscriptions) >= self.config.max_subscriptions_per_client:
                self._log.warning("Max subscriptions reached for %s", session.client_id)
                granted_qos_list.append(0x80)
                continue

            # Validate topic filter
            try:
                validate_topic_filter(topic_filter)
            except ValueError as e:
                self._log.warning("Invalid topic filter from %s: %s", session.client_id, e)
                granted_qos_list.append(0x80)
                continue

            # Check topic levels
            if hasattr(self.config, 'max_topic_levels'):
                tf_str = topic_filter.decode('utf-8') if isinstance(topic_filter, bytes) else topic_filter
                if tf_str.count('/') + 1 > self.config.max_topic_levels:
                    self._log.warning("Too many topic levels in filter from %s", session.client_id)
                    granted_qos_list.append(0x80)
                    continue

            # Cap QoS at 1 if QoS 2 is disabled
            granted_qos = requested_qos
            if not self.config.qos2_enabled and granted_qos > 1:
                granted_qos = 1

            # Authorize subscribe
            if self.auth and hasattr(self.auth, 'authorize_subscribe'):
                auth_qos = self.auth.authorize_subscribe(session.client_id, topic_filter)
                if auth_qos < 0:
                    self._log.warning("Subscribe denied for %s on %s", session.client_id, topic_filter)
                    granted_qos_list.append(0x80)
                    continue
                # Cap at authorized QoS level
                if auth_qos < granted_qos:
                    granted_qos = auth_qos

            # Fire on_subscribe hook (can modify QoS or reject)
            result = await self._fire_hook(self._on_subscribe, session.client_id, topic_filter, granted_qos)
            if result is not None:
                granted_qos = result

            # Check for rejection
            if granted_qos == 0x80:
                granted_qos_list.append(0x80)
                continue

            # Subscribe in topic tree
            self.topic_tree.subscribe(topic_filter, session.client_id, granted_qos)

            # Store in session
            if isinstance(topic_filter, bytes):
                topic_filter_str = topic_filter.decode('utf-8')
            else:
                topic_filter_str = topic_filter
            session.subscriptions[topic_filter_str] = granted_qos

            granted_qos_list.append(granted_qos)

            # Deliver retained messages
            await self.router.deliver_retained(session, topic_filter, granted_qos)

        # Send SUBACK
        suback = packet.build_suback(subscribe.packet_id, granted_qos_list)
        await session.send(suback)
        self.stats.messages_sent += 1

    async def _process_unsubscribe(self, session, data):
        """
        Process UNSUBSCRIBE packet.

        Args:
            session: ClientSession
            data: Raw packet payload
        """
        try:
            unsubscribe = packet.parse_unsubscribe(data)
        except Exception as e:
            self._log.warning("Error parsing UNSUBSCRIBE: %s", e)
            return

        for topic_filter in unsubscribe.topics:
            self.topic_tree.unsubscribe(topic_filter, session.client_id)

            if isinstance(topic_filter, bytes):
                topic_filter_str = topic_filter.decode('utf-8')
            else:
                topic_filter_str = topic_filter

            if topic_filter_str in session.subscriptions:
                del session.subscriptions[topic_filter_str]

            await self._fire_hook(self._on_unsubscribe, session.client_id, topic_filter)

        # Send UNSUBACK
        unsuback = packet.build_unsuback(unsubscribe.packet_id)
        await session.send(unsuback)
        self.stats.messages_sent += 1

    async def _process_disconnect(self, session):
        """
        Process DISCONNECT packet (clean disconnect).

        Args:
            session: ClientSession
        """
        session.will_topic = None
        session.will_message = None
        session.connected = False

        await self._fire_hook(self._on_disconnect, session.client_id, True)

    async def _process_puback(self, session, data):
        """Process PUBACK packet (QoS 1 acknowledgment)."""
        packet_id = struct.unpack_from('!H', data, 0)[0]
        self.qos_manager.handle_puback(session, packet_id)

    async def _process_pubrec(self, session, data):
        """Process PUBREC packet (QoS 2 publish received)."""
        packet_id = struct.unpack_from('!H', data, 0)[0]
        if self.qos_manager.handle_pubrec(session, packet_id):
            await session.send(packet.build_pubrel(packet_id))
            self.stats.messages_sent += 1

    async def _process_pubrel(self, session, data):
        """Process PUBREL packet (QoS 2 publish release)."""
        packet_id = struct.unpack_from('!H', data, 0)[0]
        result = self.qos_manager.handle_pubrel(session, packet_id)
        if result:
            topic, payload, retain = result
            await self.router.route_publish(topic, payload, 2, retain, session.client_id)
        await session.send(packet.build_pubcomp(packet_id))
        self.stats.messages_sent += 1

    async def _process_pubcomp(self, session, data):
        """Process PUBCOMP packet (QoS 2 publish complete)."""
        packet_id = struct.unpack_from('!H', data, 0)[0]
        self.qos_manager.handle_pubcomp(session, packet_id)

    async def _handle_disconnect(self, session, graceful=False):
        """
        Handle client disconnection and cleanup.

        Args:
            session: ClientSession
            graceful: True if client sent DISCONNECT, False if connection lost
        """
        # Publish will message if not graceful and will exists
        if not graceful and session.will_topic:
            # Fire on_will_publish hook - return False to suppress
            will_result = await self._fire_hook(
                self._on_will_publish,
                session.client_id,
                session.will_topic,
                session.will_message
            )
            if will_result is not False:
                try:
                    await self.router.route_publish(
                        session.will_topic,
                        session.will_message,
                        session.will_qos,
                        session.will_retain,
                        session.client_id
                    )
                except Exception as e:
                    self._log.error("Error publishing will message: %s", e)

            session.will_topic = None
            session.will_message = None

        # Mark as disconnected
        session.connected = False

        # Close writer
        try:
            session.writer.close()
            if hasattr(session.writer, 'wait_closed'):
                await session.writer.wait_closed()
        except (OSError, AttributeError):
            pass

        # Clean up auth state
        if self.auth and hasattr(self.auth, 'cleanup_client'):
            self.auth.cleanup_client(session.client_id)

        # Clean up if clean_session
        if session.clean_session:
            self.topic_tree.unsubscribe_all(session.client_id)
            if session.client_id in self.sessions:
                del self.sessions[session.client_id]

        self._log.info("Client disconnected: %s", session.client_id)

        # Fire on_disconnect hook if not already fired
        if not graceful:
            await self._fire_hook(self._on_disconnect, session.client_id, False)

    # Public methods

    async def publish(self, topic, payload, qos=0, retain=False):
        """
        Publish a message from the broker itself (internal publish).

        Args:
            topic: Topic name (bytes or str)
            payload: Message payload (bytes or str)
            qos: QoS level (0-2)
            retain: Retain flag
        """
        if isinstance(topic, str):
            topic = topic.encode('utf-8')
        if isinstance(payload, str):
            payload = payload.encode('utf-8')

        await self.router.route_publish(topic, payload, qos, retain, sender_id=None)
        self.stats.publishes_sent += 1

    def get_clients(self):
        """
        Get list of connected client info dicts.

        Returns:
            list of dicts with keys: client_id, username, connected, subscriptions, keep_alive
        """
        result = []
        for cid, session in self.sessions.items():
            result.append({
                'client_id': cid,
                'username': session.username,
                'connected': session.connected,
                'subscriptions': list(session.subscriptions.keys()),
                'keep_alive': session.keep_alive
            })
        return result

    async def disconnect_client(self, client_id, graceful=True):
        """
        Forcefully disconnect a client by ID.

        Args:
            client_id: Client identifier string
            graceful: If True, treat as clean disconnect (no will)

        Returns:
            True if client was found and disconnected
        """
        session = self.sessions.get(client_id)
        if session and session.connected:
            await self._handle_disconnect(session, graceful=graceful)
            return True
        return False

    def get_stats(self):
        """
        Get broker statistics as a dict.

        Returns:
            dict with message counts, uptime, connected clients, etc.
        """
        connected = self.session_manager.get_connected_count()
        return {
            'uptime': self.stats.get_uptime(),
            'clients_connected': connected,
            'clients_total': len(self.sessions),
            'messages_received': self.stats.messages_received,
            'messages_sent': self.stats.messages_sent,
            'publishes_received': self.stats.publishes_received,
            'publishes_sent': self.stats.publishes_sent,
            'bytes_received': self.stats.bytes_received,
            'bytes_sent': self.stats.bytes_sent,
            'connections_total': self.stats.connections_count,
            'subscriptions': self.topic_tree.get_subscription_count(),
            'retained_messages': self.topic_tree.get_retained_count()
        }

    def get_subscriptions(self, client_id=None):
        """
        Get active subscriptions.

        Args:
            client_id: If provided, return subscriptions for this client only.
                       If None, return all subscriptions.

        Returns:
            If client_id is given: dict {topic_filter: granted_qos, ...} or empty dict
            If client_id is None: dict {client_id: {topic_filter: granted_qos, ...}, ...}
        """
        if client_id is not None:
            session = self.sessions.get(client_id)
            if session and session.subscriptions:
                return dict(session.subscriptions)
            return {}
        result = {}
        for cid, session in self.sessions.items():
            if session.subscriptions:
                result[cid] = dict(session.subscriptions)
        return result

    def get_retained_messages(self):
        """
        Get all retained messages.

        Returns:
            list of (topic_str, payload_bytes, qos) tuples
        """
        result = []
        stack = [self.topic_tree.root]
        while stack:
            node = stack.pop()
            if node.retained is not None:
                topic_bytes, payload, qos = node.retained
                if isinstance(topic_bytes, bytes):
                    topic_str = topic_bytes.decode('utf-8')
                else:
                    topic_str = topic_bytes
                result.append((topic_str, payload, qos))
            if node.children:
                for child in node.children.values():
                    stack.append(child)
        return result

    def clear_retained(self, topic=None):
        """
        Clear retained messages.

        Args:
            topic: Specific topic to clear (str or bytes), or None for all
        """
        if topic is not None:
            self.retained_store.clear(topic)
        else:
            self.retained_store.clear()

    # Background tasks

    async def _gc_task(self):
        """Background garbage collection task."""
        while self._running:
            await asyncio.sleep(self.config.gc_collect_interval)
            gc.collect()
            try:
                gc.threshold(gc.mem_alloc() + 4096)
            except (AttributeError, NotImplementedError):
                pass

    async def _keep_alive_monitor(self):
        """Monitor client keep-alive and disconnect stale clients."""
        while self._running:
            await asyncio.sleep(5)

            for client_id in list(self.sessions.keys()):
                session = self.sessions.get(client_id)

                if session and session.connected and session.keep_alive > 0:
                    if session.is_keep_alive_expired(self.config.keep_alive_factor):
                        self._log.info("Keep-alive timeout for %s", client_id)
                        await self._handle_disconnect(session, graceful=False)

    async def _retransmit_task(self):
        """Background task for QoS 1/2 message retransmission."""
        while self._running:
            await asyncio.sleep(self.config.qos_retry_interval)
            for session in list(self.sessions.values()):
                if session.connected:
                    await self.qos_manager.retransmit_pending(session)

    async def _session_cleanup_task(self):
        """Background task for cleaning up expired offline sessions."""
        while self._running:
            await asyncio.sleep(60)
            removed = self.session_manager.cleanup_expired()
            if removed > 0:
                self._log.info("Cleaned up %d expired sessions", removed)
            # Prune empty topic tree nodes
            self.topic_tree.prune()

    async def _sys_topics_task(self):
        """Background task for publishing $SYS topics."""
        while self._running:
            await asyncio.sleep(self.config.stats_interval)

            try:
                connected = self.session_manager.get_connected_count()
                subscriptions = self.topic_tree.get_subscription_count()
                retained = self.topic_tree.get_retained_count()
                total_sessions = len(self.sessions)

                sys_topics = self.stats.get_sys_topics(
                    connected, subscriptions, retained,
                    total_sessions=total_sessions
                )

                for topic, value in sys_topics.items():
                    topic_bytes = topic.encode('utf-8')
                    payload_bytes = value.encode('utf-8')
                    # Publish $SYS as retained QoS 0
                    await self.router.route_publish(
                        topic_bytes, payload_bytes, 0, True, sender_id=None
                    )
            except Exception as e:
                self._log.error("Error publishing $SYS topics: %s", e)

    async def shutdown(self):
        """Shutdown the broker and close all connections."""
        self._log.info("Shutting down broker...")
        self._running = False

        # Disconnect all clients
        for client_id in list(self.sessions.keys()):
            session = self.sessions.get(client_id)
            if session and session.connected:
                await self._handle_disconnect(session, graceful=False)

        # Close server
        if self._server:
            self._server.close()
            if hasattr(self._server, 'wait_closed'):
                await self._server.wait_closed()

        # Cancel background tasks
        for task in self._tasks:
            try:
                task.cancel()
            except Exception:
                pass

        self._log.info("Broker stopped")
