import asyncio
import json
import logging
from typing import Dict, Any, Optional

from simulator.core.node import Node, Host, Router, Switch
from simulator.core.link import Link
from simulator.engine.clock import SimulationClock
from simulator.engine.event_bus import EventBus
from simulator.routing.engine import RoutingEngine

logger = logging.getLogger(__name__)

class NetworkController:
    """The central orchestrator of the network simulation."""
    
    def __init__(self, scenario_name: str = "Unknown"):
        self.scenario_name = scenario_name
        self.nodes: Dict[str, Node] = {}
        self.links: Dict[str, Link] = {}
        self.event_bus = EventBus()
        self.clock = SimulationClock()
        self.running = False
        self._node_tasks: list[asyncio.Task] = []
        self._action_tasks: list[asyncio.Task] = []
        self.routing_engine = RoutingEngine()

    async def load_scenario(self, path: str):
        """Loads a scenario from a JSON file and builds the topology."""
        logger.info(f"Loading scenario from {path}")
        
        with open(path, 'r') as f:
            scenario_config = json.load(f)

        self.scenario_name = scenario_config.get("name", "Unnamed Scenario")
        self.clock.tick_interval = scenario_config.get("tick_rate", 0.1)

        self._build_nodes(scenario_config.get("nodes", []))
        self._build_links(scenario_config.get("links", []))

        self.routing_engine.setup_routes(list(self.nodes.values()), list(self.links.values()))
        
        for action in scenario_config.get("actions", []):
            self._action_tasks.append(action)
            
        logger.info(f"Loaded scenario {self.scenario_name}: {len(self.nodes)} nodes, {len(self.links)} links")

    def _build_nodes(self, node_configs: list[Dict[str, Any]]):
        for config in node_configs:
            node_id = config["id"]
            node_type = config["type"].lower()
            
            if node_type == "host":
                node = Host(node_id, self.event_bus)
                if "gateway" in config:
                    node.gateway_ip = config["gateway"]
            elif node_type == "router":
                node = Router(node_id, self.event_bus)
                for route_config in config.get("routes", []):
                    from simulator.routing.table import RouteEntry
                    entry = RouteEntry(
                        network=route_config["network"],
                        next_hop=route_config.get("next_hop"),
                        interface=route_config["interface"],
                        metric=route_config.get("metric", 1)
                    )
                    node.routing_table.add_route(entry)
            elif node_type == "switch":
                node = Switch(node_id, self.event_bus)
            else:
                logger.warning(f"Unknown node type: {node_type}")
                continue

            for iface_config in config.get("interfaces", []):
                from simulator.core.node import Interface
                iface = Interface(
                    name=iface_config["name"],
                    mac=iface_config.get("mac", ""),
                    ip=iface_config.get("ip"),
                    mask=iface_config.get("mask")
                )
                node.interfaces.append(iface)
                
            self.nodes[node_id] = node

    def _build_links(self, link_configs: list[Dict[str, Any]]):
        for config in link_configs:
            link_id = config["id"]
            ep_a = config["endpoints"][0].split(".")
            ep_b = config["endpoints"][1].split(".")
            
            if len(ep_a) != 2 or len(ep_b) != 2:
                logger.error(f"Invalid endpoint format for link {link_id}")
                continue
                
            node_a, iface_a = ep_a
            node_b, iface_b = ep_b
            
            link = Link(
                id=link_id,
                bandwidth=config.get("bandwidth", 1000000000),
                latency=config.get("latency", 1),
                loss_rate=config.get("loss_rate", 0.0),
                endpoint_a=(node_a, iface_a),
                endpoint_b=(node_b, iface_b),
                controller=self
            )
            self.links[link_id] = link
            
            if node_a in self.nodes:
                iface = self.nodes[node_a].get_interface(iface_a)
                if iface:
                    iface.link = link
            if node_b in self.nodes:
                iface = self.nodes[node_b].get_interface(iface_b)
                if iface:
                    iface.link = link

    async def start(self):
        """Starts the simulation."""
        logger.info("Starting simulation")
        self.running = True
        
        # Start nodes
        for node in self.nodes.values():
            task = asyncio.create_task(node.run())
            self._node_tasks.append(task)
            
        # Run scheduled actions
        for action in self._action_tasks:
            if action["type"] == "ping":
                asyncio.create_task(self._scheduled_ping(action))
                
        # Start clock
        asyncio.create_task(self.clock.run(self._on_tick))
        
        await self.event_bus.emit({"event_type": "SIMULATION_START", "timestamp": self.clock.elapsed_time, "data": {}})

    async def stop(self):
        """Stops the simulation."""
        logger.info("Stopping simulation")
        self.running = False
        self.clock.running = False
        
        for node in self.nodes.values():
            node.running = False
            
        for task in self._node_tasks:
            task.cancel()
            
        self._node_tasks.clear()
        await self.event_bus.emit({"event_type": "SIMULATION_STOP", "timestamp": self.clock.elapsed_time, "data": {}})

    async def step(self):
        """Advances the simulation by one tick."""
        if not self.running:
            return
        await self.clock.step()

    async def reset(self):
        """Resets the simulation state."""
        await self.stop()
        self.nodes.clear()
        self.links.clear()
        self.clock.reset()

    async def _on_tick(self, tick: int):
        await self.event_bus.emit({
            "event_type": "SIMULATION_TICK",
            "timestamp": self.clock.elapsed_time,
            "data": {"tick": tick}
        })

    async def _scheduled_ping(self, action: Dict[str, Any]):
        delay = action.get("delay", 0)
        await asyncio.sleep(delay)
        
        from_node_id = action.get("from")
        target_ip = action.get("to")
        count = action.get("count", 4)
        
        await self.inject_ping(from_node_id, target_ip, count)

    async def inject_ping(self, from_node_id: str, target_ip: str, count: int = 4, interval: float = 1.0):
        """Injects a ping command into a host."""
        if from_node_id not in self.nodes:
            logger.error(f"Ping source node not found: {from_node_id}")
            return
            
        node = self.nodes[from_node_id]
        if not isinstance(node, Host):
            logger.error(f"Ping source must be a Host, got {type(node)}")
            return
            
        for i in range(count):
            if not self.running:
                break
            await node.ping(target_ip)
            await asyncio.sleep(interval)

    def get_topology_snapshot(self) -> Dict[str, Any]:
        """Returns the full topology state."""
        return {
            "scenario": self.scenario_name,
            "nodes": {n_id: node.to_dict() for n_id, node in self.nodes.items()},
            "links": {l_id: link.to_dict() for l_id, link in self.links.items()}
        }

    def get_stats(self) -> Dict[str, Any]:
        """Returns aggregate simulation statistics."""
        return {
            "tick": self.clock.current_tick,
            "elapsed": self.clock.elapsed_time,
            "nodes": len(self.nodes),
            "links": len(self.links)
        }
