"""
Core package — re-exports fundamental data models.
"""

from simulator.core.packet import Packet, PacketType, BROADCAST_MAC
from simulator.core.link import Link, LinkStats, Endpoint
from simulator.core.node import (
    Node,
    Host,
    Router,
    Switch,
    Interface,
    NodeType,
    ARPCacheEntry,
)

__all__ = [
    "Packet",
    "PacketType",
    "BROADCAST_MAC",
    "Link",
    "LinkStats",
    "Endpoint",
    "Node",
    "Host",
    "Router",
    "Switch",
    "Interface",
    "NodeType",
    "ARPCacheEntry",
]
