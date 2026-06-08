"""
Plugin manager — discovers, loads, and dispatches lifecycle events to plugins.
"""

from __future__ import annotations

import importlib.util
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from simulator.plugins.base import SimPlugin

if TYPE_CHECKING:
    from simulator.engine.controller import NetworkController
    from simulator.engine.event_bus import NetworkEvent

logger = logging.getLogger(__name__)


class PluginManager:
    """Discovers and manages :class:`SimPlugin` instances.

    Plugins are Python files that contain a concrete subclass of
    :class:`SimPlugin`.  The manager scans a directory, imports each
    ``.py`` file, finds ``SimPlugin`` subclasses, instantiates them,
    and calls :meth:`~SimPlugin.on_load`.
    """

    def __init__(self) -> None:
        self.plugins: list[SimPlugin] = []

    def load_plugins(self, directory: str | Path, controller: NetworkController) -> None:
        """Scan *directory* for ``.py`` files containing plugins.

        Args:
            directory: Path to the plugin directory.
            controller: The simulation controller to pass to ``on_load``.
        """
        plugin_dir = Path(directory)
        if not plugin_dir.is_dir():
            logger.warning("Plugin directory does not exist: %s", plugin_dir)
            return

        for path in sorted(plugin_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                self._load_file(path, controller)
            except Exception:
                logger.exception("Failed to load plugin from %s", path)

    def _load_file(self, path: Path, controller: NetworkController) -> None:
        """Import *path* and instantiate any SimPlugin subclasses found."""
        spec = importlib.util.spec_from_file_location(
            f"netsim_plugin_{path.stem}", path
        )
        if spec is None or spec.loader is None:
            logger.warning("Cannot create module spec for %s", path)
            return

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]

        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, SimPlugin)
                and attr is not SimPlugin
            ):
                plugin = attr()
                plugin.on_load(controller)
                self.plugins.append(plugin)
                logger.info(
                    "Loaded plugin: %s v%s — %s",
                    plugin.name,
                    plugin.version,
                    plugin.description,
                )

    def unload_all(self) -> None:
        """Unload all plugins, calling :meth:`~SimPlugin.on_unload`."""
        for plugin in self.plugins:
            try:
                plugin.on_unload()
            except Exception:
                logger.exception("Error unloading plugin %s", plugin.name)
        self.plugins.clear()

    async def notify_tick(self, tick: int) -> None:
        """Dispatch a tick event to all plugins.

        Args:
            tick: The current tick number.
        """
        for plugin in self.plugins:
            try:
                await plugin.on_tick(tick)
            except Exception:
                logger.exception(
                    "Plugin %s error on tick %d", plugin.name, tick
                )

    async def notify_packet(self, event: NetworkEvent) -> None:
        """Dispatch a packet event to all plugins.

        Args:
            event: The network event.
        """
        for plugin in self.plugins:
            try:
                await plugin.on_packet(event)
            except Exception:
                logger.exception(
                    "Plugin %s error on event %s",
                    plugin.name,
                    event.event_type,
                )
