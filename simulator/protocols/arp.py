"""
ARP protocol handler.

Implements Address Resolution Protocol logic: responding to ARP requests
addressed to the local node, caching ARP replies, and providing an async
:meth:`resolve` helper that sends a request and waits for the reply.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from simulator.core.packet import Packet, PacketType, BROADCAST_MAC
from simulator.protocols.base import Protocol, Action, ActionType

if TYPE_CHECKING:
    from simulator.core.node import Node, Interface

logger = logging.getLogger(__name__)


class ARPProtocol(Protocol):
    """ARP request/reply handler."""

    @property
    def name(self) -> str:
        return "ARP"

    async def handle(
        self,
        node: Node,
        packet: Packet,
        ingress_interface: Interface,
    ) -> list[Action]:
        """Handle an ARP_REQUEST or ARP_REPLY.

        On ARP_REQUEST for one of our IPs: generate an ARP_REPLY.
        On ARP_REPLY: update the node's ARP cache.

        Returns:
            List of :class:`Action` objects.
        """
        actions: list[Action] = []

        if packet.packet_type == PacketType.ARP_REQUEST:
            target_ip = packet.payload.get("target_ip", packet.dst_ip)

            # Always learn the sender
            node.arp_update(packet.src_ip, packet.src_mac)

            if node.has_ip(target_ip):
                iface = node.get_interface_by_ip(target_ip) or ingress_interface
                reply = Packet.arp_reply(
                    src_mac=iface.mac,
                    src_ip=target_ip,
                    dst_mac=packet.src_mac,
                    dst_ip=packet.src_ip,
                )
                actions.append(
                    Action(
                        action_type=ActionType.RESPOND,
                        packet=reply,
                        target_interface=ingress_interface.name,
                    )
                )

        elif packet.packet_type == PacketType.ARP_REPLY:
            node.arp_update(packet.src_ip, packet.src_mac)
            logger.debug(
                "%s: ARP cache updated %s -> %s",
                node.id, packet.src_ip, packet.src_mac,
            )
            actions.append(Action(action_type=ActionType.DROP, packet=packet))

        return actions

    @staticmethod
    async def resolve(
        node: Node,
        target_ip: str,
        source_interface: Interface,
        timeout: float = 3.0,
    ) -> str | None:
        """Resolve *target_ip* to a MAC address, sending an ARP request if needed.

        Args:
            node: The requesting node.
            target_ip: IP to resolve.
            source_interface: Interface to send the ARP request from.
            timeout: Maximum seconds to wait for a reply.

        Returns:
            The resolved MAC address, or ``None`` on timeout.
        """
        cached = node.arp_lookup(target_ip)
        if cached is not None:
            return cached

        # Build and send ARP request
        req = Packet.arp_request(
            src_mac=source_interface.mac,
            src_ip=source_interface.ip or "",
            target_ip=target_ip,
        )

        event = asyncio.Event()
        node._arp_waiters.setdefault(target_ip, []).append(event)

        await node._send_packet(req, source_interface)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "%s: ARP resolve timeout for %s", node.id, target_ip
            )
            return None

        return node.arp_lookup(target_ip)
