"""
Core packet definitions for the network simulator.

Defines the ``Packet`` dataclass that flows through the simulated network, the
``PacketType`` enum for classifying traffic, and convenient factory methods for
creating ARP, ICMP, and generic IP packets.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


BROADCAST_MAC: str = "ff:ff:ff:ff:ff:ff"
"""Ethernet broadcast MAC address used by ARP requests and floods."""



class PacketType(Enum):
    """Enumeration of recognised packet types within the simulator."""

    ARP_REQUEST = auto()
    ARP_REPLY = auto()
    ICMP_ECHO_REQUEST = auto()
    ICMP_ECHO_REPLY = auto()
    ICMP_TIME_EXCEEDED = auto()
    ICMP_DEST_UNREACHABLE = auto()
    IP_DATA = auto()



@dataclass
class Packet:
    """Represents a single network packet traversing the simulated topology.

    Attributes:
        id: Short unique identifier (first 8 hex chars of a UUID4).
        packet_type: Semantic type of the packet (ARP, ICMP, …).
        src_mac: Source MAC address.
        dst_mac: Destination MAC address.
        src_ip: Source IP address (dotted-quad string).
        dst_ip: Destination IP address (dotted-quad string).
        ttl: Time-to-live counter; decremented by routers.
        payload: Arbitrary key/value data carried inside the packet.
        timestamp: Unix timestamp when the packet was created.
        hops: Ordered list of node IDs that this packet has visited.
    """

    packet_type: PacketType
    src_mac: str
    dst_mac: str
    src_ip: str
    dst_ip: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    ttl: int = 64
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    hops: list[str] = field(default_factory=list)

    # ---- Factory class methods --------------------------------------------

    @classmethod
    def arp_request(
        cls,
        src_mac: str,
        src_ip: str,
        target_ip: str,
    ) -> Packet:
        """Create an ARP request broadcast packet.

        Args:
            src_mac: MAC address of the requesting host.
            src_ip: IP address of the requesting host.
            target_ip: IP address whose MAC is being resolved.

        Returns:
            A new ``Packet`` with ``PacketType.ARP_REQUEST``.
        """
        return cls(
            packet_type=PacketType.ARP_REQUEST,
            src_mac=src_mac,
            dst_mac=BROADCAST_MAC,
            src_ip=src_ip,
            dst_ip=target_ip,
            ttl=1,
            payload={"target_ip": target_ip},
        )

    @classmethod
    def arp_reply(
        cls,
        src_mac: str,
        src_ip: str,
        dst_mac: str,
        dst_ip: str,
    ) -> Packet:
        """Create a unicast ARP reply.

        Args:
            src_mac: MAC of the node responding.
            src_ip: IP of the node responding.
            dst_mac: MAC of the original requester.
            dst_ip: IP of the original requester.

        Returns:
            A new ``Packet`` with ``PacketType.ARP_REPLY``.
        """
        return cls(
            packet_type=PacketType.ARP_REPLY,
            src_mac=src_mac,
            dst_mac=dst_mac,
            src_ip=src_ip,
            dst_ip=dst_ip,
            ttl=1,
            payload={"resolved_mac": src_mac, "resolved_ip": src_ip},
        )

    @classmethod
    def icmp_echo(
        cls,
        src_mac: str,
        dst_mac: str,
        src_ip: str,
        dst_ip: str,
        sequence: int = 0,
    ) -> Packet:
        """Create an ICMP Echo Request (ping).

        Args:
            src_mac: Source MAC address.
            dst_mac: Destination MAC address.
            src_ip: Source IP address.
            dst_ip: Destination IP address.
            sequence: ICMP sequence number.

        Returns:
            A new ``Packet`` with ``PacketType.ICMP_ECHO_REQUEST``.
        """
        return cls(
            packet_type=PacketType.ICMP_ECHO_REQUEST,
            src_mac=src_mac,
            dst_mac=dst_mac,
            src_ip=src_ip,
            dst_ip=dst_ip,
            payload={"sequence": sequence, "send_time": time.time()},
        )

    @classmethod
    def icmp_reply(cls, request: Packet) -> Packet:
        """Create an ICMP Echo Reply from an existing echo request.

        The source/destination MAC and IP are swapped relative to the request.

        Args:
            request: The original ``ICMP_ECHO_REQUEST`` packet.

        Returns:
            A new ``Packet`` with ``PacketType.ICMP_ECHO_REPLY``.
        """
        return cls(
            packet_type=PacketType.ICMP_ECHO_REPLY,
            src_mac=request.dst_mac,
            dst_mac=request.src_mac,
            src_ip=request.dst_ip,
            dst_ip=request.src_ip,
            payload={
                "sequence": request.payload.get("sequence", 0),
                "send_time": request.payload.get("send_time", 0.0),
                "reply_time": time.time(),
            },
        )


    def to_dict(self) -> dict[str, Any]:
        """Serialise the packet to a plain dictionary suitable for JSON.

        Returns:
            Dictionary representation of this packet.
        """
        return {
            "id": self.id,
            "packet_type": self.packet_type.name,
            "src_mac": self.src_mac,
            "dst_mac": self.dst_mac,
            "src_ip": self.src_ip,
            "dst_ip": self.dst_ip,
            "ttl": self.ttl,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "hops": list(self.hops),
        }

    def __repr__(self) -> str:
        return (
            f"Packet(id={self.id!r}, type={self.packet_type.name}, "
            f"src={self.src_ip}->{self.dst_ip}, ttl={self.ttl})"
        )
