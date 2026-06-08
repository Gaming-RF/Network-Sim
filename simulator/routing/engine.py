"""
Routing engine — automatic route setup for the simulated topology.

:class:`RoutingEngine` inspects router interfaces and scenario configuration
to populate each router's :class:`RoutingTable` with directly-connected
and static routes.  Host default gateways are also wired.
"""

from __future__ import annotations

import ipaddress
import logging
from typing import TYPE_CHECKING

from simulator.routing.table import RouteEntry

if TYPE_CHECKING:
    from simulator.core.node import Node, Router, Host
    from simulator.core.link import Link

logger = logging.getLogger(__name__)


class RoutingEngine:
    """Static routing setup helper.

    Call :meth:`setup_routes` after nodes and links have been created to
    populate every router's routing table with directly-connected subnets
    and any static routes declared in the scenario file.
    """

    @staticmethod
    def setup_routes(
        nodes: dict[str, Node],
        links: dict[str, Link],
        static_routes: dict[str, list[dict]] | None = None,
    ) -> None:
        """Populate routing tables for all routers and host gateways.

        Args:
            nodes: Mapping of node_id → Node.
            links: Mapping of link_id → Link (currently unused but available
                for future dynamic-routing algorithms).
            static_routes: Optional mapping of router_id → list of route dicts
                with keys ``network``, ``next_hop``, ``interface``, ``metric``.
        """
        from simulator.core.node import Router, Host

        static_routes = static_routes or {}

        for node in nodes.values():
            if isinstance(node, Router):
                RoutingEngine._setup_router_routes(node, static_routes.get(node.id, []))
            elif isinstance(node, Host):
                RoutingEngine._setup_host_gateway(node)

    @staticmethod
    def _setup_router_routes(
        router: Router,
        extra_routes: list[dict],
    ) -> None:
        """Add directly-connected and static routes to *router*.

        Args:
            router: The router to configure.
            extra_routes: Additional static routes from the scenario.
        """
        # Directly-connected subnets
        for iface in router.interfaces:
            if iface.ip and iface.mask:
                try:
                    net = ipaddress.IPv4Network(
                        f"{iface.ip}/{iface.mask}", strict=False
                    )
                    entry = RouteEntry(
                        network=str(net),
                        next_hop="",  # directly connected
                        interface=iface.name,
                        metric=0,
                    )
                    router.routing_table.add_route(entry)
                    logger.info(
                        "%s: connected route %s dev %s",
                        router.id, net, iface.name,
                    )
                except (ipaddress.AddressValueError, ValueError) as exc:
                    logger.warning(
                        "%s: invalid interface address %s/%s: %s",
                        router.id, iface.ip, iface.mask, exc,
                    )

        # Static routes from scenario
        for rd in extra_routes:
            entry = RouteEntry(
                network=rd["network"],
                next_hop=rd.get("next_hop", ""),
                interface=rd.get("interface", ""),
                metric=rd.get("metric", 1),
            )
            router.routing_table.add_route(entry)
            logger.info(
                "%s: static route %s via %s dev %s metric %d",
                router.id,
                entry.network,
                entry.next_hop,
                entry.interface,
                entry.metric,
            )

    @staticmethod
    def _setup_host_gateway(host: Host) -> None:
        """Log (and validate) the host's default gateway setting.

        Args:
            host: The host node.
        """
        if host.gateway_ip:
            logger.info(
                "%s: default gateway %s", host.id, host.gateway_ip
            )
        else:
            logger.debug("%s: no gateway configured", host.id)
