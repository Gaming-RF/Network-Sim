"""
ICMP protocol handler.

Handles Echo Request / Echo Reply, Time Exceeded, and Destination
Unreachable messages.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from simulator.core.packet import Packet, PacketType
from simulator.protocols.base import Protocol, Action, ActionType

if TYPE_CHECKING:
    from simulator.core.node import Node, Interface

logger = logging.getLogger(__name__)


class ICMPProtocol(Protocol):
    """Handler for all ``ICMP_*`` packet types."""

    @property
    def name(self) -> str:
        return "ICMP"

    async def handle(
        self,
        node: Node,
        packet: Packet,
        ingress_interface: Interface,
    ) -> list[Action]:
        """Process ICMP packets.

        * ``ECHO_REQUEST`` destined for us → generate ``ECHO_REPLY``.
        * ``ECHO_REPLY`` → log and deliver (resolve pending futures).
        * ``TIME_EXCEEDED`` / ``DEST_UNREACHABLE`` → log.

        Returns:
            List of :class:`Action` objects.
        """
        actions: list[Action] = []

        if packet.packet_type == PacketType.ICMP_ECHO_REQUEST:
            if node.has_ip(packet.dst_ip):
                reply = Packet.icmp_reply(packet)
                iface = node.get_interface_by_ip(packet.dst_ip) or ingress_interface
                reply.src_mac = iface.mac
                reply.dst_mac = packet.src_mac
                actions.append(
                    Action(
                        action_type=ActionType.RESPOND,
                        packet=reply,
                        target_interface=ingress_interface.name,
                    )
                )
            else:
                # Not for us — could forward (handled by IP protocol)
                actions.append(
                    Action(action_type=ActionType.FORWARD, packet=packet)
                )

        elif packet.packet_type == PacketType.ICMP_ECHO_REPLY:
            rtt = (time.time() - packet.payload.get("send_time", time.time())) * 1000
            logger.info(
                "%s: ICMP reply from %s seq=%s rtt=%.2fms",
                node.id,
                packet.src_ip,
                packet.payload.get("sequence", "?"),
                rtt,
            )
            actions.append(Action(action_type=ActionType.DROP, packet=packet))

        elif packet.packet_type == PacketType.ICMP_TIME_EXCEEDED:
            logger.info(
                "%s: ICMP Time Exceeded from %s (original dst: %s)",
                node.id,
                packet.src_ip,
                packet.payload.get("original_dst", "?"),
            )
            actions.append(Action(action_type=ActionType.DROP, packet=packet))

        elif packet.packet_type == PacketType.ICMP_DEST_UNREACHABLE:
            logger.info(
                "%s: ICMP Destination Unreachable from %s (dst: %s)",
                node.id,
                packet.src_ip,
                packet.payload.get("original_dst", "?"),
            )
            actions.append(Action(action_type=ActionType.DROP, packet=packet))

        return actions
