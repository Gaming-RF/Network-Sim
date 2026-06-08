"""
IP protocol handler.

Performs TTL decrementation, routing-table lookup, next-hop ARP resolution,
and packet forwarding for generic IP data packets.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from simulator.core.packet import Packet, PacketType
from simulator.protocols.base import Protocol, Action, ActionType

if TYPE_CHECKING:
    from simulator.core.node import Node, Interface

logger = logging.getLogger(__name__)


class IPProtocol(Protocol):
    """Handler for ``PacketType.IP_DATA`` packets."""

    @property
    def name(self) -> str:
        return "IP"

    async def handle(
        self,
        node: Node,
        packet: Packet,
        ingress_interface: Interface,
    ) -> list[Action]:
        """Decrement TTL, lookup route, and build forwarding actions.

        If TTL reaches zero an ``ICMP_TIME_EXCEEDED`` response is created
        and the original packet is dropped.

        Returns:
            List of :class:`Action` objects.
        """
        actions: list[Action] = []

        # Decrement TTL
        packet.ttl -= 1
        if packet.ttl <= 0:
            logger.info(
                "%s: TTL exceeded for %s -> %s",
                node.id, packet.src_ip, packet.dst_ip,
            )
            # Generate ICMP Time Exceeded
            te = Packet(
                packet_type=PacketType.ICMP_TIME_EXCEEDED,
                src_mac=ingress_interface.mac,
                dst_mac=packet.src_mac,
                src_ip=ingress_interface.ip or "",
                dst_ip=packet.src_ip,
                payload={
                    "original_packet_id": packet.id,
                    "original_dst": packet.dst_ip,
                },
            )
            actions.append(
                Action(
                    action_type=ActionType.RESPOND,
                    packet=te,
                    target_interface=ingress_interface.name,
                )
            )
            actions.append(Action(action_type=ActionType.DROP, packet=packet))
            return actions

        # Route lookup (only on routers)
        from simulator.core.node import Router

        if isinstance(node, Router):
            route = node.routing_table.lookup(packet.dst_ip)
            if route is None:
                logger.info("%s: no route to %s", node.id, packet.dst_ip)
                dest_unreach = Packet(
                    packet_type=PacketType.ICMP_DEST_UNREACHABLE,
                    src_mac=ingress_interface.mac,
                    dst_mac=packet.src_mac,
                    src_ip=ingress_interface.ip or "",
                    dst_ip=packet.src_ip,
                    payload={"original_dst": packet.dst_ip},
                )
                actions.append(
                    Action(
                        action_type=ActionType.RESPOND,
                        packet=dest_unreach,
                        target_interface=ingress_interface.name,
                    )
                )
                actions.append(Action(action_type=ActionType.DROP, packet=packet))
                return actions

            actions.append(
                Action(
                    action_type=ActionType.FORWARD,
                    packet=packet,
                    target_interface=route.interface,
                )
            )
        else:
            # Non-router: just drop
            actions.append(Action(action_type=ActionType.DROP, packet=packet))

        return actions
