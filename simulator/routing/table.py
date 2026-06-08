"""
Routing table implementation with longest-prefix-match lookup.

Provides the ``RouteEntry`` dataclass for individual routes and the
``RoutingTable`` class that stores them and performs longest-prefix-match
lookups using the standard library :mod:`ipaddress` module.
"""

from __future__ import annotations

import ipaddress
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# RouteEntry

@dataclass
class RouteEntry:
    """A single entry in a routing table.

    Attributes:
        network: CIDR notation of the destination network (e.g. ``"10.0.1.0/24"``).
        next_hop: IP address of the next-hop router, or ``""`` for directly-connected.
        interface: Name of the egress interface.
        metric: Administrative distance / cost (lower is preferred).
    """

    network: str
    next_hop: str
    interface: str
    metric: int = 0

    # Cached parsed network (not serialised)
    _net: ipaddress.IPv4Network | None = field(default=None, repr=False, compare=False)

    @property
    def net(self) -> ipaddress.IPv4Network:
        """Parsed :class:`~ipaddress.IPv4Network` for this entry."""
        if self._net is None:
            self._net = ipaddress.IPv4Network(self.network, strict=False)
        return self._net

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dictionary."""
        return {
            "network": self.network,
            "next_hop": self.next_hop,
            "interface": self.interface,
            "metric": self.metric,
        }


# RoutingTable

class RoutingTable:
    """An ordered collection of ``RouteEntry`` objects with LPM lookup.

    Routes are stored in a simple list and evaluated by longest prefix match.
    For equal prefix lengths the lowest metric wins.
    """

    def __init__(self) -> None:
        self.entries: list[RouteEntry] = []

    # -- mutations -----------------------------------------------------------

    def add_route(self, entry: RouteEntry) -> None:
        """Insert a route, keeping the list sorted by prefix length descending.

        Args:
            entry: The route to add.
        """
        # Ensure the internal _net cache is populated
        _ = entry.net
        self.entries.append(entry)
        # Sort: longest prefix first, then lowest metric
        self.entries.sort(key=lambda e: (-e.net.prefixlen, e.metric))
        logger.debug("Route added: %s via %s dev %s", entry.network, entry.next_hop, entry.interface)

    def remove_route(self, network: str) -> bool:
        """Remove all routes matching *network* (CIDR string).

        Args:
            network: The CIDR network to remove.

        Returns:
            ``True`` if at least one route was removed.
        """
        target = ipaddress.IPv4Network(network, strict=False)
        before = len(self.entries)
        self.entries = [e for e in self.entries if e.net != target]
        removed = len(self.entries) < before
        if removed:
            logger.debug("Route removed: %s", network)
        return removed

    # -- lookup -------------------------------------------------------------

    def lookup(self, destination_ip: str) -> RouteEntry | None:
        """Perform a longest-prefix-match lookup for *destination_ip*.

        Args:
            destination_ip: Dotted-quad IPv4 address string.

        Returns:
            The best matching ``RouteEntry``, or ``None`` if no route matches.
        """
        try:
            addr = ipaddress.IPv4Address(destination_ip)
        except (ipaddress.AddressValueError, ValueError):
            logger.warning("Invalid destination IP for lookup: %s", destination_ip)
            return None

        for entry in self.entries:  # already sorted longest-prefix-first
            if addr in entry.net:
                return entry
        return None


    def to_dict(self) -> list[dict[str, Any]]:
        """Return a JSON-serialisable list of all route entries."""
        return [e.to_dict() for e in self.entries]

    def __len__(self) -> int:
        return len(self.entries)

    def __repr__(self) -> str:
        return f"RoutingTable(entries={len(self.entries)})"
