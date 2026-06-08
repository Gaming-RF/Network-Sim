import asyncio
import argparse
import logging
import signal
import sys

from simulator.engine.controller import NetworkController
from simulator.server.ws_server import SimulationServer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger("netsim")

async def async_main():
    parser = argparse.ArgumentParser(description="NetSim - Network Simulator")
    parser.add_argument("--scenario", type=str, help="Path to scenario JSON/YAML file", required=True)
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Listen host")
    parser.add_argument("--port", type=int, default=8765, help="Listen port")
    parser.add_argument("--headless", action="store_true", help="Run without web server")
    parser.add_argument("--ticks", type=int, default=0, help="Run for N ticks then exit (0 = forever)")
    parser.add_argument("--daemon", action="store_true", help="Run in daemon mode (restart on crash)")
    
    args = parser.parse_args()

    controller = NetworkController()
    
    server = None
    if not args.headless:
        server = SimulationServer(controller)

    loop = asyncio.get_running_loop()
    
    shutdown_event = asyncio.Event()

    def handle_signal():
        logger.info("Received termination signal, shutting down...")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, handle_signal)
        except NotImplementedError:
            # signal handlers not supported on Windows
            pass

    while True:
        try:
            await controller.load_scenario(args.scenario)
            
            if server:
                await server.start(args.host, args.port)
                
            await controller.start()
            
            if args.ticks > 0:
                logger.info(f"Running for {args.ticks} ticks...")
                while controller.clock.current_tick < args.ticks and not shutdown_event.is_set():
                    await asyncio.sleep(0.1)
                shutdown_event.set()
            else:
                await shutdown_event.wait()
                
            break # Normal exit
            
        except Exception as e:
            logger.error(f"Simulator crashed: {e}", exc_info=True)
            if args.daemon:
                logger.info("Daemon mode enabled, restarting in 5 seconds...")
                await controller.stop()
                await asyncio.sleep(5)
                shutdown_event.clear()
            else:
                break
                
    await controller.stop()
    logger.info("Shutdown complete.")

def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
