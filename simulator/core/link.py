"""
Network link model for the simulator.

A ``Link`` connects two node interfaces and models bandwidth, latency, and
random packet loss.  Each call to :meth:`transmit` asynchronously sleeps
for the configured latency period before delivering the packet to the far-end
node's inbox queue.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.core.packet import Packet

logger = logging.getLogger(__name__)

# Link statistics


@dataclass
class LinkStats:
    """Counters kept per link for telemetry/reporting."""

    bytes_sent: int = 0
    packets_sent: int = 0
    packets_dropped: int = 0

    def to_dict(self) -> dict[str, int]:
        """Serialise statistics to a plain dictionary."""
        return {
            "bytes_sent": self.bytes_sent,
            "packets_sent": self.packets_sent,
            "packets_dropped": self.packets_dropped,
        }


# Endpoint type alias

Endpoint = tuple[str, str]  # (node_id, interface_name)




@dataclass
class Link:
    """A bidirectional Ethernet-like link between two node interfaces.

    Attributes:
        id: Unique link identifier.
        bandwidth: Maximum throughput in bits per second (informational).
        latency: Propagation delay in *milliseconds*.
        loss_rate: Probability (0.0 – 1.0) that a transmitted packet is lost.
        endpoint_a: ``(node_id, interface_name)`` of one side.
        endpoint_b: ``(node_id, interface_name)`` of the other side.
        stats: Cumulative transmission statistics.
    """

    id: str
    bandwidth: int  # bps
    latency: float  # ms
    loss_rate: float  # 0.0 – 1.0
    endpoint_a: Endpoint
    endpoint_b: Endpoint
    stats: LinkStats = field(default_factory=LinkStats)

    # -- runtime refs (set during wiring) -----------------------------------
    _node_queues: dict[str, asyncio.Queue[Any]] = field(
        default_factory=dict, repr=False
    )

    def register_node_queue(self, node_id: str, queue: asyncio.Queue[Any]) -> None:
        """Register a node's inbox queue so *transmit* can deliver packets.

        Args:
            node_id: Identifier of the node.
            queue: The node's asyncio inbox queue.
        """
        self._node_queues[node_id] = queue

    # -- helpers -----------------------------------------------------------

    def get_other_endpoint(self, node_id: str) -> Endpoint:
        """Return the endpoint on the far side of the link.

        Args:
            node_id: The node whose *other* endpoint you want.

        Returns:
            The ``(node_id, interface_name)`` tuple on the opposite end.

        Raises:
            ValueError: If *node_id* is not attached to this link.
        """
        if self.endpoint_a[0] == node_id:
            return self.endpoint_b
        if self.endpoint_b[0] == node_id:
            return self.endpoint_a
        raise ValueError(
            f"Node {node_id!r} is not an endpoint of link {self.id!r}"
        )

    def get_local_interface(self, node_id: str) -> str:
        """Return the interface name on *this* side for *node_id*.

        Args:
            node_id: The node whose local interface you want.

        Returns:
            Interface name string.

        Raises:
            ValueError: If *node_id* is not attached to this link.
        """
        if self.endpoint_a[0] == node_id:
            return self.endpoint_a[1]
        if self.endpoint_b[0] == node_id:
            return self.endpoint_b[1]
        raise ValueError(
            f"Node {node_id!r} is not an endpoint of link {self.id!r}"
        )

    # -- transmission -------------------------------------------------------

    async def transmit(self, packet: Packet, from_node_id: str) -> bool:
        """Simulate sending *packet* across the link from *from_node_id*.

        The method:
        1. Applies propagation latency via ``asyncio.sleep``.
        2. Simulates random loss according to ``loss_rate``.
        3. On success, puts the packet into the far-end node's inbox.

        Args:
            packet: The packet to transmit.
            from_node_id: The originating node's identifier.

        Returns:
            ``True`` if the packet was delivered, ``False`` if it was dropped.
        """
        other_node_id, other_iface = self.get_other_endpoint(from_node_id)

        # Simulate propagation delay
        if self.latency > 0:
            await asyncio.sleep(self.latency / 1000.0)

        # Simulate random loss
        if self.loss_rate > 0 and random.random() < self.loss_rate:
            self.stats.packets_dropped += 1
            logger.debug(
                "Link %s: dropped packet %s (loss_rate=%.3f)",
                self.id,
                packet.id,
                self.loss_rate,
            )
            return False

        # Deliver to far-end node
        queue = self._node_queues.get(other_node_id)
        if queue is None:
            logger.warning(
                "Link %s: no inbox registered for node %s", self.id, other_node_id
            )
            self.stats.packets_dropped += 1
            return False

        self.stats.packets_sent += 1
        # Rough byte count (fixed overhead for simplicity)
        self.stats.bytes_sent += 64

        await queue.put((packet, other_iface))
        logger.debug(
            "Link %s: delivered packet %s -> %s:%s",
            self.id,
            packet.id,
            other_node_id,
            other_iface,
        )
        return True


    def to_dict(self) -> dict[str, Any]:
        """Serialise the link to a plain dictionary suitable for JSON.

        Returns:
            Dictionary representation of this link.
        """
        return {
            "id": self.id,
            "bandwidth": self.bandwidth,
            "latency": self.latency,
            "loss_rate": self.loss_rate,
            "endpoint_a": {
                "node_id": self.endpoint_a[0],
                "interface": self.endpoint_a[1],
            },
            "endpoint_b": {
                "node_id": self.endpoint_b[0],
                "interface": self.endpoint_b[1],
            },
            "stats": self.stats.to_dict(),
        }

    def __repr__(self) -> str:
        return (
            f"Link(id={self.id!r}, "
            f"{self.endpoint_a[0]}:{self.endpoint_a[1]} <-> "
            f"{self.endpoint_b[0]}:{self.endpoint_b[1]}, "
            f"latency={self.latency}ms, loss={self.loss_rate})"
        )
