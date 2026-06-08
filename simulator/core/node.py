"""
Network node models — Host, Router, and Switch.

Provides the abstract :class:`Node` base class and its three concrete
implementations: :class:`Host`, :class:`Router`, and :class:`Switch`.
Each node owns an :class:`asyncio.Queue` *inbox* and runs a main loop that
dequeues incoming packets and dispatches them to :meth:`process_packet`.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, TYPE_CHECKING

from simulator.core.packet import Packet, PacketType, BROADCAST_MAC
from simulator.routing.table import RoutingTable, RouteEntry

if TYPE_CHECKING:
    from simulator.core.link import Link
    from simulator.engine.event_bus import EventBus

logger = logging.getLogger(__name__)

# Enums & dataclasses


class NodeType(Enum):
    """Type discriminator for the three kinds of nodes."""

    HOST = auto()
    ROUTER = auto()
    SWITCH = auto()


@dataclass
class Interface:
    """A network interface attached to a :class:`Node`.

    Attributes:
        name: Short human-readable name (``eth0``, ``port0``, …).
        mac: MAC address in colon-hex notation.
        ip: Optional IPv4 address (dotted-quad string).
        mask: Optional subnet mask (dotted-quad string).
        link: Optional reference to the :class:`Link` this interface is
            connected to.
    """

    name: str
    mac: str
    ip: str | None = None
    mask: str | None = None
    link: Link | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        """Serialise interface metadata (excludes heavy link ref)."""
        return {
            "name": self.name,
            "mac": self.mac,
            "ip": self.ip,
            "mask": self.mask,
            "link_id": self.link.id if self.link else None,
        }


# ARP cache entry

@dataclass
class ARPCacheEntry:
    """An entry in a node's ARP cache."""

    mac: str
    expires: float  # Unix timestamp

    ARP_TIMEOUT: float = 120.0  # seconds

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires


# Abstract Node


class Node(ABC):
    """Abstract base class for all network nodes.

    Every node has:
    * a unique *id*
    * one or more :class:`Interface` objects
    * an :class:`asyncio.Queue` inbox
    * an ARP cache mapping IP → MAC
    * a reference to the simulation :class:`EventBus`

    Subclasses must implement :meth:`process_packet`.
    """

    def __init__(
        self,
        node_id: str,
        node_type: NodeType,
        interfaces: list[Interface],
        event_bus: EventBus | None = None,
    ) -> None:
        self.id = node_id
        self.node_type = node_type
        self.interfaces = interfaces
        self.inbox: asyncio.Queue[tuple[Packet, str]] = asyncio.Queue()
        self.running = False
        self.arp_cache: dict[str, ARPCacheEntry] = {}
        self.event_bus: EventBus | None = event_bus

        # ARP resolution waiters: ip -> list of asyncio.Event
        self._arp_waiters: dict[str, list[asyncio.Event]] = {}

        # Pending ping tracking: packet_id -> asyncio.Future
        self._pending_pings: dict[str, asyncio.Future[Packet]] = {}


    def get_interface(self, name: str) -> Interface | None:
        """Return the interface with the given *name*, or ``None``."""
        for iface in self.interfaces:
            if iface.name == name:
                return iface
        return None

    def get_interface_by_mac(self, mac: str) -> Interface | None:
        """Return the interface with the given *mac*, or ``None``."""
        for iface in self.interfaces:
            if iface.mac == mac:
                return iface
        return None

    def get_interface_by_ip(self, ip: str) -> Interface | None:
        """Return the interface whose IP matches *ip*, or ``None``."""
        for iface in self.interfaces:
            if iface.ip == ip:
                return iface
        return None

    def has_ip(self, ip: str) -> bool:
        """Check whether any interface on this node owns *ip*."""
        return any(iface.ip == ip for iface in self.interfaces)

    # -- ARP cache helpers --------------------------------------------------

    def arp_lookup(self, ip: str) -> str | None:
        """Look up *ip* in the ARP cache, returning the MAC or ``None`` if
        the entry is missing or expired."""
        entry = self.arp_cache.get(ip)
        if entry is None or entry.is_expired:
            self.arp_cache.pop(ip, None)
            return None
        return entry.mac

    def arp_update(self, ip: str, mac: str) -> None:
        """Insert or refresh an ARP cache entry."""
        self.arp_cache[ip] = ARPCacheEntry(
            mac=mac,
            expires=time.time() + ARPCacheEntry.ARP_TIMEOUT,
        )
        # Wake any waiters for this IP
        for evt in self._arp_waiters.pop(ip, []):
            evt.set()


    async def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        """Convenience wrapper to emit an event on the bus."""
        if self.event_bus is not None:
            from simulator.engine.event_bus import NetworkEvent

            await self.event_bus.emit(
                NetworkEvent(event_type=event_type, data=data, source_node=self.id)
            )


    async def _send_packet(self, packet: Packet, egress_iface: Interface) -> None:
        """Transmit *packet* out of *egress_iface* via its attached link.

        Args:
            packet: The packet to send.
            egress_iface: The interface to send out of.
        """
        if egress_iface.link is None:
            logger.warning(
                "%s: interface %s has no link, dropping packet %s",
                self.id, egress_iface.name, packet.id,
            )
            return

        packet.hops.append(self.id)
        await self._emit("packet.sent", {
            "packet": packet.to_dict(),
            "interface": egress_iface.name,
        })

        asyncio.create_task(
            egress_iface.link.transmit(packet, self.id)
        )

    # -- main loop ----------------------------------------------------------

    async def run(self) -> None:
        """Main processing loop — dequeue packets and dispatch them.

        Runs until :attr:`running` is set to ``False``.
        """
        self.running = True
        logger.info("Node %s (%s) started", self.id, self.node_type.name)
        try:
            while self.running:
                try:
                    packet, ingress_iface_name = await asyncio.wait_for(
                        self.inbox.get(), timeout=0.5
                    )
                except asyncio.TimeoutError:
                    continue

                ingress_iface = self.get_interface(ingress_iface_name)
                if ingress_iface is None:
                    logger.warning(
                        "%s: received packet on unknown interface %s",
                        self.id, ingress_iface_name,
                    )
                    continue

                await self._emit("packet.received", {
                    "packet": packet.to_dict(),
                    "interface": ingress_iface_name,
                })

                try:
                    await self.process_packet(packet, ingress_iface)
                except Exception:
                    logger.exception(
                        "%s: error processing packet %s", self.id, packet.id
                    )
        except asyncio.CancelledError:
            logger.info("Node %s: run loop cancelled", self.id)
        finally:
            self.running = False
            logger.info("Node %s stopped", self.id)

    @abstractmethod
    async def process_packet(self, packet: Packet, ingress: Interface) -> None:
        """Handle an incoming *packet* that arrived on *ingress*.

        Args:
            packet: The received packet.
            ingress: The interface the packet arrived on.
        """


    def to_dict(self) -> dict[str, Any]:
        """Base serialisation — subclasses extend with their own state."""
        return {
            "id": self.id,
            "node_type": self.node_type.name,
            "interfaces": [i.to_dict() for i in self.interfaces],
            "arp_cache": {
                ip: entry.mac
                for ip, entry in self.arp_cache.items()
                if not entry.is_expired
            },
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(id={self.id!r})"


# Host


class Host(Node):
    """An endpoint host that can originate and respond to ARP and ICMP.

    Attributes:
        gateway_ip: Default gateway IP for off-subnet destinations.
    """

    def __init__(
        self,
        node_id: str,
        interfaces: list[Interface],
        gateway_ip: str | None = None,
        event_bus: EventBus | None = None,
    ) -> None:
        super().__init__(node_id, NodeType.HOST, interfaces, event_bus)
        self.gateway_ip = gateway_ip

    async def process_packet(self, packet: Packet, ingress: Interface) -> None:
        """Handle ARP and ICMP packets addressed to this host."""
        if packet.packet_type == PacketType.ARP_REQUEST:
            await self._handle_arp_request(packet, ingress)
        elif packet.packet_type == PacketType.ARP_REPLY:
            await self._handle_arp_reply(packet, ingress)
        elif packet.packet_type == PacketType.ICMP_ECHO_REQUEST:
            await self._handle_icmp_echo_request(packet, ingress)
        elif packet.packet_type == PacketType.ICMP_ECHO_REPLY:
            await self._handle_icmp_echo_reply(packet, ingress)
        elif packet.packet_type in (
            PacketType.ICMP_TIME_EXCEEDED,
            PacketType.ICMP_DEST_UNREACHABLE,
        ):
            logger.info(
                "%s: received %s from %s",
                self.id, packet.packet_type.name, packet.src_ip,
            )
        else:
            logger.debug(
                "%s: ignoring packet type %s", self.id, packet.packet_type.name
            )

    # -- ARP handlers -------------------------------------------------------

    async def _handle_arp_request(self, packet: Packet, ingress: Interface) -> None:
        """Respond to ARP requests targeting one of our IPs."""
        target_ip = packet.payload.get("target_ip", packet.dst_ip)
        # Learn the sender
        self.arp_update(packet.src_ip, packet.src_mac)

        if self.has_ip(target_ip):
            iface = self.get_interface_by_ip(target_ip)
            if iface is None:
                iface = ingress
            reply = Packet.arp_reply(
                src_mac=iface.mac,
                src_ip=target_ip,
                dst_mac=packet.src_mac,
                dst_ip=packet.src_ip,
            )
            await self._emit("arp.reply", {
                "packet": reply.to_dict(),
                "resolved_ip": target_ip,
                "resolved_mac": iface.mac,
            })
            await self._send_packet(reply, ingress)

    async def _handle_arp_reply(self, packet: Packet, _ingress: Interface) -> None:
        """Cache the resolved MAC from an ARP reply."""
        self.arp_update(packet.src_ip, packet.src_mac)
        await self._emit("arp.resolved", {
            "ip": packet.src_ip,
            "mac": packet.src_mac,
        })
        logger.info(
            "%s: ARP resolved %s -> %s", self.id, packet.src_ip, packet.src_mac
        )

    # -- ICMP handlers ------------------------------------------------------

    async def _handle_icmp_echo_request(
        self, packet: Packet, ingress: Interface
    ) -> None:
        """Reply to ICMP echo requests destined for us."""
        if not self.has_ip(packet.dst_ip):
            return  # Not for us

        reply = Packet.icmp_reply(packet)
        # Rewrite MACs with our own
        iface = self.get_interface_by_ip(packet.dst_ip) or ingress
        reply.src_mac = iface.mac
        reply.dst_mac = packet.src_mac

        await self._emit("icmp.reply", {"packet": reply.to_dict()})
        await self._send_packet(reply, ingress)

    async def _handle_icmp_echo_reply(
        self, packet: Packet, _ingress: Interface
    ) -> None:
        """Deliver an ICMP echo reply to any waiting ping future."""
        rtt = (time.time() - packet.payload.get("send_time", time.time())) * 1000
        logger.info(
            "%s: ICMP reply from %s seq=%s rtt=%.2fms",
            self.id,
            packet.src_ip,
            packet.payload.get("sequence", "?"),
            rtt,
        )
        await self._emit("ping.result", {
            "from": self.id,
            "target": packet.src_ip,
            "sequence": packet.payload.get("sequence", 0),
            "rtt_ms": round(rtt, 2),
            "ttl": packet.ttl,
        })
        # Resolve any pending ping future
        fut = self._pending_pings.pop(packet.id, None)
        if fut and not fut.done():
            fut.set_result(packet)

    # -- ping ---------------------------------------------------------------

    async def ping(self, target_ip: str, count: int = 4, interval: float = 1.0) -> None:
        """Originate ICMP echo request(s) to *target_ip*.

        If the target is on a different subnet, the host ARPs for its
        default gateway instead.

        Args:
            target_ip: Destination IP to ping.
            count: Number of echo requests to send.
            interval: Seconds between successive pings.
        """
        # Choose the source interface (first with an IP)
        src_iface = next((i for i in self.interfaces if i.ip), None)
        if src_iface is None:
            logger.error("%s: no interface with an IP to ping from", self.id)
            return

        # Determine if target is on the same subnet
        next_hop_ip = target_ip
        if src_iface.ip and src_iface.mask:
            src_net = ipaddress.IPv4Network(
                f"{src_iface.ip}/{src_iface.mask}", strict=False
            )
            if ipaddress.IPv4Address(target_ip) not in src_net:
                if self.gateway_ip:
                    next_hop_ip = self.gateway_ip
                else:
                    logger.error(
                        "%s: no gateway configured for off-subnet ping", self.id
                    )
                    return

        # ARP resolve
        dst_mac = await self._arp_resolve(next_hop_ip, src_iface)
        if dst_mac is None:
            logger.error(
                "%s: ARP resolution failed for %s", self.id, next_hop_ip
            )
            await self._emit("ping.result", {
                "from": self.id,
                "target": target_ip,
                "error": f"ARP resolution failed for {next_hop_ip}",
            })
            return

        for seq in range(count):
            pkt = Packet.icmp_echo(
                src_mac=src_iface.mac,
                dst_mac=dst_mac,
                src_ip=src_iface.ip or "",
                dst_ip=target_ip,
                sequence=seq,
            )
            await self._emit("icmp.echo", {"packet": pkt.to_dict()})
            await self._send_packet(pkt, src_iface)
            if seq < count - 1:
                await asyncio.sleep(interval)

    async def _arp_resolve(
        self, ip: str, iface: Interface, timeout: float = 3.0
    ) -> str | None:
        """Resolve *ip* to a MAC via the ARP cache or by sending a request.

        Args:
            ip: The IP address to resolve.
            iface: The interface to send the ARP request on.
            timeout: Seconds to wait for a reply.

        Returns:
            The resolved MAC address, or ``None`` on timeout.
        """
        cached = self.arp_lookup(ip)
        if cached is not None:
            return cached

        # Send ARP request
        req = Packet.arp_request(
            src_mac=iface.mac,
            src_ip=iface.ip or "",
            target_ip=ip,
        )
        await self._emit("arp.request", {"packet": req.to_dict()})

        # Set up waiter
        event = asyncio.Event()
        self._arp_waiters.setdefault(ip, []).append(event)

        await self._send_packet(req, iface)

        # Wait for ARP reply
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s: ARP timeout for %s", self.id, ip)
            return None

        return self.arp_lookup(ip)


    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["gateway_ip"] = self.gateway_ip
        return d


# Router


class Router(Node):
    """A layer-3 router that forwards packets between subnets.

    Maintains a :class:`RoutingTable` and an ARP cache.  Decrements TTL
    on every forwarded packet and generates ICMP Time Exceeded when TTL
    reaches zero.
    """

    def __init__(
        self,
        node_id: str,
        interfaces: list[Interface],
        event_bus: EventBus | None = None,
    ) -> None:
        super().__init__(node_id, NodeType.ROUTER, interfaces, event_bus)
        self.routing_table = RoutingTable()

    async def process_packet(self, packet: Packet, ingress: Interface) -> None:
        """Route, forward, or respond to the packet."""
        # Learn ARP from every packet that arrives
        if packet.src_ip and packet.src_ip != "0.0.0.0":
            self.arp_update(packet.src_ip, packet.src_mac)

        if packet.packet_type == PacketType.ARP_REQUEST:
            await self._handle_arp_request(packet, ingress)
            return
        if packet.packet_type == PacketType.ARP_REPLY:
            await self._handle_arp_reply(packet, ingress)
            return

        # For ICMP directed at one of our IPs, respond directly
        if packet.packet_type == PacketType.ICMP_ECHO_REQUEST and self.has_ip(packet.dst_ip):
            reply = Packet.icmp_reply(packet)
            iface = self.get_interface_by_ip(packet.dst_ip) or ingress
            reply.src_mac = iface.mac
            reply.dst_mac = packet.src_mac
            await self._emit("icmp.reply", {"packet": reply.to_dict()})
            await self._send_packet(reply, ingress)
            return

        # Otherwise forward
        await self._forward_packet(packet, ingress)

    # -- ARP -----------------------------------------------------------------

    async def _handle_arp_request(self, packet: Packet, ingress: Interface) -> None:
        target_ip = packet.payload.get("target_ip", packet.dst_ip)
        self.arp_update(packet.src_ip, packet.src_mac)

        if self.has_ip(target_ip):
            iface = self.get_interface_by_ip(target_ip) or ingress
            reply = Packet.arp_reply(
                src_mac=iface.mac,
                src_ip=target_ip,
                dst_mac=packet.src_mac,
                dst_ip=packet.src_ip,
            )
            await self._emit("arp.reply", {
                "packet": reply.to_dict(),
                "resolved_ip": target_ip,
                "resolved_mac": iface.mac,
            })
            await self._send_packet(reply, ingress)

    async def _handle_arp_reply(self, packet: Packet, _ingress: Interface) -> None:
        self.arp_update(packet.src_ip, packet.src_mac)
        await self._emit("arp.resolved", {
            "ip": packet.src_ip,
            "mac": packet.src_mac,
        })

    # -- Forwarding ----------------------------------------------------------

    async def _forward_packet(self, packet: Packet, ingress: Interface) -> None:
        """Decrement TTL, look up route, ARP-resolve next hop, and forward."""
        # TTL check
        packet.ttl -= 1
        if packet.ttl <= 0:
            logger.info(
                "%s: TTL exceeded for packet %s from %s",
                self.id, packet.id, packet.src_ip,
            )
            await self._send_time_exceeded(packet, ingress)
            await self._emit("packet.dropped", {
                "packet": packet.to_dict(),
                "reason": "TTL exceeded",
            })
            return

        # Route lookup
        route = self.routing_table.lookup(packet.dst_ip)
        if route is None:
            logger.info(
                "%s: no route to %s, dropping packet %s",
                self.id, packet.dst_ip, packet.id,
            )
            await self._emit("packet.dropped", {
                "packet": packet.to_dict(),
                "reason": "No route to host",
            })
            return

        egress = self.get_interface(route.interface)
        if egress is None:
            logger.error(
                "%s: route points to unknown interface %s", self.id, route.interface
            )
            return

        # Determine next-hop IP
        next_hop_ip = route.next_hop if route.next_hop else packet.dst_ip

        # ARP resolve
        dst_mac = await self._arp_resolve(next_hop_ip, egress)
        if dst_mac is None:
            logger.warning(
                "%s: ARP failed for %s, dropping packet %s",
                self.id, next_hop_ip, packet.id,
            )
            await self._emit("packet.dropped", {
                "packet": packet.to_dict(),
                "reason": f"ARP resolution failed for {next_hop_ip}",
            })
            return

        # Rewrite L2 headers
        packet.src_mac = egress.mac
        packet.dst_mac = dst_mac

        await self._emit("packet.forwarded", {
            "packet": packet.to_dict(),
            "ingress": ingress.name,
            "egress": egress.name,
            "next_hop": next_hop_ip,
        })
        await self._send_packet(packet, egress)

    async def _send_time_exceeded(
        self, original: Packet, ingress: Interface
    ) -> None:
        """Send an ICMP Time Exceeded back to the source."""
        iface = ingress
        te_pkt = Packet(
            packet_type=PacketType.ICMP_TIME_EXCEEDED,
            src_mac=iface.mac,
            dst_mac=original.src_mac,
            src_ip=iface.ip or "",
            dst_ip=original.src_ip,
            payload={
                "original_packet_id": original.id,
                "original_dst": original.dst_ip,
            },
        )
        await self._send_packet(te_pkt, ingress)

    async def _arp_resolve(
        self, ip: str, iface: Interface, timeout: float = 3.0
    ) -> str | None:
        """Resolve *ip* to a MAC via cache or ARP request."""
        cached = self.arp_lookup(ip)
        if cached is not None:
            return cached

        req = Packet.arp_request(
            src_mac=iface.mac,
            src_ip=iface.ip or "",
            target_ip=ip,
        )
        await self._emit("arp.request", {"packet": req.to_dict()})

        event = asyncio.Event()
        self._arp_waiters.setdefault(ip, []).append(event)

        await self._send_packet(req, iface)

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("%s: ARP timeout for %s", self.id, ip)
            return None

        return self.arp_lookup(ip)


    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["routing_table"] = self.routing_table.to_dict()
        return d


# Switch


class Switch(Node):
    """A layer-2 Ethernet switch.

    Learns source MACs and forwards frames to the correct port, or floods
    all ports (except ingress) when the destination MAC is unknown or is
    the broadcast address.
    """

    def __init__(
        self,
        node_id: str,
        interfaces: list[Interface],
        event_bus: EventBus | None = None,
    ) -> None:
        super().__init__(node_id, NodeType.SWITCH, interfaces, event_bus)
        self.mac_table: dict[str, str] = {}  # mac -> interface_name

    async def process_packet(self, packet: Packet, ingress: Interface) -> None:
        """Learn source MAC and forward or flood."""
        # Learn source MAC
        if packet.src_mac and packet.src_mac != BROADCAST_MAC:
            if self.mac_table.get(packet.src_mac) != ingress.name:
                self.mac_table[packet.src_mac] = ingress.name
                logger.debug(
                    "%s: learned %s on %s", self.id, packet.src_mac, ingress.name
                )

        # Record hop
        packet.hops.append(self.id)

        # Forward or flood
        if packet.dst_mac == BROADCAST_MAC or packet.dst_mac not in self.mac_table:
            # Flood to all ports except ingress
            await self._flood(packet, ingress)
        else:
            # Unicast forward
            target_iface_name = self.mac_table[packet.dst_mac]
            target_iface = self.get_interface(target_iface_name)
            if target_iface and target_iface.link:
                await self._emit("packet.forwarded", {
                    "packet": packet.to_dict(),
                    "ingress": ingress.name,
                    "egress": target_iface_name,
                })
                await target_iface.link.transmit(packet, self.id)
            else:
                logger.warning(
                    "%s: no link on interface %s for MAC %s",
                    self.id, target_iface_name, packet.dst_mac,
                )

    async def _flood(self, packet: Packet, ingress: Interface) -> None:
        """Send *packet* out of every port except *ingress*."""
        tasks = []
        for iface in self.interfaces:
            if iface.name == ingress.name:
                continue
            if iface.link is None:
                continue
            tasks.append(iface.link.transmit(packet, self.id))

        if tasks:
            await self._emit("packet.forwarded", {
                "packet": packet.to_dict(),
                "ingress": ingress.name,
                "egress": "flood",
            })
            await asyncio.gather(*tasks)


    def to_dict(self) -> dict[str, Any]:
        d = super().to_dict()
        d["mac_table"] = dict(self.mac_table)
        return d
