"""
Event bus for decoupled, async publish/subscribe communication.

The ``EventBus`` allows any component to emit ``NetworkEvent`` instances and
any number of subscribers to react.  Subscribers register for specific event
types or the ``"*"`` wildcard to receive *all* events.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)

# Event type constants

PACKET_SENT: str = "packet.sent"
PACKET_RECEIVED: str = "packet.received"
PACKET_DROPPED: str = "packet.dropped"
PACKET_FORWARDED: str = "packet.forwarded"
ARP_REQUEST: str = "arp.request"
ARP_REPLY: str = "arp.reply"
ARP_RESOLVED: str = "arp.resolved"
ICMP_ECHO: str = "icmp.echo"
ICMP_REPLY: str = "icmp.reply"
LINK_TRANSMIT: str = "link.transmit"
SIMULATION_TICK: str = "simulation.tick"
SIMULATION_START: str = "simulation.start"
SIMULATION_STOP: str = "simulation.stop"
NODE_STATE_CHANGE: str = "node.state_change"
PING_RESULT: str = "ping.result"



@dataclass
class NetworkEvent:
    """An event emitted through the ``EventBus``.

    Attributes:
        event_type: One of the string constants defined above, or a custom type.
        timestamp: Unix timestamp when the event was created.
        data: Arbitrary payload dictionary.
        source_node: Identifier of the node that originated the event (if any).
    """

    event_type: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    source_node: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dictionary representation."""
        return {
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "data": self.data,
            "source_node": self.source_node,
        }


# Callback type alias

EventCallback = Callable[[NetworkEvent], Awaitable[None]]


# EventBus

class EventBus:
    """Thread-safe, async publish/subscribe event bus.

    Subscribers register with :meth:`on` for a specific event type string
    (or ``"*"`` for all events).  When :meth:`emit` is called the bus
    invokes every matching callback concurrently.

    The bus uses an :class:`asyncio.Lock` to protect its subscriber
    dictionary so that subscriptions can be modified while events are
    being dispatched.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventCallback]] = {}
        self._lock = asyncio.Lock()

    async def on(self, event_type: str, callback: EventCallback) -> None:
        """Register *callback* for *event_type*.

        Args:
            event_type: The event type string, or ``"*"`` for all events.
            callback: An async callable ``(NetworkEvent) -> None``.
        """
        async with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    async def off(self, event_type: str, callback: EventCallback) -> None:
        """Unregister *callback* from *event_type*.

        Args:
            event_type: The event type originally passed to :meth:`on`.
            callback: The exact callback reference to remove.
        """
        async with self._lock:
            cbs = self._subscribers.get(event_type, [])
            try:
                cbs.remove(callback)
            except ValueError:
                pass

    async def emit(self, event: NetworkEvent) -> None:
        """Dispatch *event* to all matching subscribers.

        Both subscribers for the specific ``event.event_type`` *and*
        wildcard ``"*"`` subscribers are invoked.

        Args:
            event: The event to broadcast.
        """
        async with self._lock:
            specific = list(self._subscribers.get(event.event_type, []))
            wildcard = list(self._subscribers.get("*", []))

        callbacks = specific + wildcard
        if not callbacks:
            return

        results = await asyncio.gather(
            *(cb(event) for cb in callbacks), return_exceptions=True
        )
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    "EventBus callback error for %s: %s",
                    event.event_type,
                    result,
                    exc_info=result,
                )

    def subscriber_count(self, event_type: str | None = None) -> int:
        """Return the number of subscribers, optionally filtered by type.

        Args:
            event_type: If given, count only subscribers for this type.

        Returns:
            Integer subscriber count.
        """
        if event_type is not None:
            return len(self._subscribers.get(event_type, []))
        return sum(len(v) for v in self._subscribers.values())
