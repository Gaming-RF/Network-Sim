"""
Plugins package — re-exports plugin types.
"""

from simulator.plugins.base import SimPlugin
from simulator.plugins.manager import PluginManager

__all__ = ["SimPlugin", "PluginManager"]
