import asyncio
import json
import logging
import os
from aiohttp import web
from typing import Set

from simulator.engine.controller import NetworkController

logger = logging.getLogger(__name__)

class SimulationServer:
    """HTTP and WebSocket server for the network simulator."""
    
    def __init__(self, controller: NetworkController):
        self.controller = controller
        self.app = web.Application()
        self.clients: Set[web.WebSocketResponse] = set()
        
        # Setup routes
        self.app.router.add_get('/ws', self.websocket_handler)
        
        # Serve static files from ../web
        web_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'web'))
        if os.path.exists(web_dir):
            self.app.router.add_static('/', web_dir, show_index=True)
            logger.info(f"Serving static files from {web_dir}")
        else:
            logger.warning(f"Static web directory not found: {web_dir}")

        # Subscribe to all events
        self.controller.event_bus.on("*", self.broadcast_event)

    async def start(self, host="0.0.0.0", port=8765):
        """Starts the server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, host, port)
        await site.start()
        logger.info(f"Server started on http://{host}:{port}")

    async def websocket_handler(self, request):
        """Handles new WebSocket connections."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        self.clients.add(ws)
        logger.info("New WebSocket client connected")
        
        # Send initial state
        try:
            await ws.send_json({
                "event": "topology_snapshot",
                "data": self.controller.get_topology_snapshot()
            })
            
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    await self.handle_command(msg.data, ws)
                elif msg.type == web.WSMsgType.ERROR:
                    logger.error(f"WebSocket connection closed with exception {ws.exception()}")
        finally:
            self.clients.remove(ws)
            logger.info("WebSocket client disconnected")
            
        return ws

    async def handle_command(self, payload: str, ws: web.WebSocketResponse):
        """Parses and executes client commands."""
        try:
            data = json.loads(payload)
            command = data.get("command")
            args = data.get("args", {})
            
            if command == "start":
                await self.controller.start()
            elif command == "stop":
                await self.controller.stop()
            elif command == "step":
                await self.controller.step()
            elif command == "reset":
                await self.controller.reset()
                await ws.send_json({
                    "event": "topology_snapshot",
                    "data": self.controller.get_topology_snapshot()
                })
            elif command == "ping":
                await self.controller.inject_ping(
                    from_node_id=args.get("from"),
                    target_ip=args.get("to"),
                    count=args.get("count", 1)
                )
            elif command == "load_scenario":
                path = args.get("path")
                if path:
                    await self.controller.reset()
                    await self.controller.load_scenario(path)
                    await ws.send_json({
                        "event": "topology_snapshot",
                        "data": self.controller.get_topology_snapshot()
                    })
            elif command == "get_state":
                 await ws.send_json({
                    "event": "topology_snapshot",
                    "data": self.controller.get_topology_snapshot()
                })
            else:
                logger.warning(f"Unknown command received: {command}")
                
        except Exception as e:
            logger.error(f"Error handling command: {e}")

    async def broadcast_event(self, event: dict):
        """Broadcasts an event to all connected clients."""
        if not self.clients:
            return
            
        # Convert event_type to event to match client expectation
        ws_msg = {
            "event": event.get("event_type", "UNKNOWN").lower(),
            "data": event.get("data", {}),
            "timestamp": event.get("timestamp", 0)
        }
        
        msg_str = json.dumps(ws_msg)
        
        # Gather all send operations to run concurrently
        tasks = [asyncio.create_task(self._send_to_client(ws, msg_str)) for ws in self.clients]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _send_to_client(self, ws: web.WebSocketResponse, msg_str: str):
        try:
            await ws.send_str(msg_str)
        except Exception as e:
             # Disconnections are handled in the websocket_handler
             pass
