"""
Protocol base classes and action definitions.

Every protocol handler extends :class:`Protocol` and returns a list of
:class:`Action` objects describing what the node should do with the packet
(forward, drop, respond, or broadcast).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.core.node import Node, Interface
    from simulator.core.packet import Packet


# Action types


class ActionType(Enum):
    """What to do with a packet after protocol processing."""

    FORWARD = auto()
    DROP = auto()
    RESPOND = auto()
    BROADCAST = auto()


@dataclass
class Action:
    """An instruction returned by a :class:`Protocol` handler.

    Attributes:
        action_type: The action to take.
        packet: The packet to operate on (may be a newly created reply).
        target_interface: Optional interface name for directed forwarding.
    """

    action_type: ActionType
    packet: Packet
    target_interface: str | None = None


# Abstract Protocol


class Protocol(ABC):
    """Abstract base for protocol handlers.

    Each implementation declares a :attr:`name` and provides an
    :meth:`handle` method that inspects the incoming packet and returns
    a list of :class:`Action` objects.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable protocol name."""

    @abstractmethod
    async def handle(
        self,
        node: Node,
        packet: Packet,
        ingress_interface: Interface,
    ) -> list[Action]:
        """Process *packet* arriving on *ingress_interface* at *node*.

        Args:
            node: The node that received the packet.
            packet: The received packet.
            ingress_interface: The interface it arrived on.

        Returns:
            A (possibly empty) list of :class:`Action` objects.
        """
