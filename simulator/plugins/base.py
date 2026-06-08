"""
Plugin base class.

Third-party or built-in plugins subclass :class:`SimPlugin` to hook into
the simulation lifecycle: load, unload, tick, and packet events.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.engine.controller import NetworkController
    from simulator.engine.event_bus import NetworkEvent


class SimPlugin(ABC):
    """Abstract base for simulator plugins.

    Every plugin must declare :attr:`name`, :attr:`version`, and
    :attr:`description` properties and implement :meth:`on_load`.
    The remaining lifecycle hooks have default no-op implementations.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable plugin name."""

    @property
    def version(self) -> str:
        """Semantic version string (default ``"0.1.0"``)."""
        return "0.1.0"

    @property
    def description(self) -> str:
        """Short description of what the plugin does."""
        return ""

    # -- lifecycle hooks ----------------------------------------------------

    @abstractmethod
    def on_load(self, controller: NetworkController) -> None:
        """Called when the plugin is loaded.

        Use this to subscribe to events, register custom commands, etc.

        Args:
            controller: The simulation controller.
        """

    def on_unload(self) -> None:
        """Called when the plugin is unloaded. Clean up resources here."""

    async def on_tick(self, tick: int) -> None:
        """Called on every simulation tick.

        Args:
            tick: The current tick number.
        """

    async def on_packet(self, event: NetworkEvent) -> None:
        """Called when a packet event is emitted.

        Args:
            event: The network event.
        """
