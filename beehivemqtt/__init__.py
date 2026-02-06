"""
BeehiveMQTT - Native MQTT 3.1.1 Broker for MicroPython

The first and only native MQTT broker running directly on ESP32.
"""

__version__ = '1.0.0'
__author__ = 'mateuszsury'

from .broker import MQTTBroker, MessageContext
from .simple import BeehiveBrokerSimple
from .config import BrokerConfig
from .errors import MQTTError, MQTTProtocolError, MQTTAuthError, MQTTConnectionError, MQTTPayloadError
from .topic import TopicTree
from .router import MessageRouter
from .auth import AuthProvider, DictAuthProvider, ACLAuthProvider, CallbackAuthProvider
from .ratelimit import RateLimiter

# Convenience aliases
BeehiveBroker = MQTTBroker
MQTTBrokerSimple = BeehiveBrokerSimple
