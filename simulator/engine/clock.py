"""
Simulation clock with pause, resume, step, and speed control.

The :class:`SimulationClock` drives the discrete-time simulation loop,
calling a user-supplied async callback on every tick.  The effective tick
rate can be scaled with :attr:`speed_multiplier`.
"""

from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class SimulationClock:
    """A simple wall-clock-driven simulation tick generator.

    Attributes:
        current_tick: The current tick counter (starts at 0).
        tick_interval: Nominal seconds between ticks.
        running: ``True`` while the clock loop is active.
        paused: ``True`` when the clock is paused (ticks stop advancing).
        speed_multiplier: Factor by which to accelerate (>1) or decelerate (<1)
            the tick rate.  The actual sleep is ``tick_interval / speed_multiplier``.
    """

    def __init__(self, tick_interval: float = 0.1, speed_multiplier: float = 1.0) -> None:
        self.current_tick: int = 0
        self.tick_interval: float = tick_interval
        self.running: bool = False
        self.paused: bool = False
        self.speed_multiplier: float = speed_multiplier
        self._step_event: asyncio.Event = asyncio.Event()

    @property
    def elapsed_time(self) -> float:
        """Simulated elapsed time in seconds."""
        return self.current_tick * self.tick_interval


    def pause(self) -> None:
        """Pause the clock.  Ticks stop advancing until :meth:`resume` is called."""
        self.paused = True
        logger.info("Clock paused at tick %d", self.current_tick)

    def resume(self) -> None:
        """Resume the clock after a pause."""
        self.paused = False
        logger.info("Clock resumed at tick %d", self.current_tick)

    def step(self) -> None:
        """Advance exactly one tick while paused."""
        self._step_event.set()

    def reset(self) -> None:
        """Reset the tick counter to zero."""
        self.current_tick = 0
        self.paused = False
        logger.info("Clock reset")

    def stop(self) -> None:
        """Stop the clock loop entirely."""
        self.running = False
        # Unblock if stuck in a pause wait
        self._step_event.set()

    # -- main loop -----------------------------------------------------------

    async def run(self, callback: asyncio.coroutines = None) -> None:  # type: ignore[assignment]
        """Run the clock loop, invoking *callback(tick)* on each tick.

        Args:
            callback: An async callable receiving the current tick number.
                May be ``None`` (no-op ticks).
        """
        self.running = True
        logger.info(
            "Clock started: interval=%.3fs, speed=%.1fx",
            self.tick_interval,
            self.speed_multiplier,
        )

        try:
            while self.running:
                if self.paused:
                    # Wait until step() or resume()
                    self._step_event.clear()
                    await self._step_event.wait()
                    if not self.running:
                        break
                    if self.paused:
                        # Single step
                        self.current_tick += 1
                        if callback:
                            await callback(self.current_tick)
                        continue

                actual_interval = self.tick_interval / max(self.speed_multiplier, 0.01)
                await asyncio.sleep(actual_interval)

                if not self.running:
                    break

                self.current_tick += 1
                if callback:
                    await callback(self.current_tick)

        except asyncio.CancelledError:
            logger.info("Clock cancelled at tick %d", self.current_tick)
        finally:
            self.running = False
            logger.info("Clock stopped at tick %d", self.current_tick)
