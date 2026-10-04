"""The sole MAVSDK/PX4 boundary for VoiceDrone flight execution."""

import asyncio
import contextlib
import math
from typing import Any

from mavsdk import System
from mavsdk.offboard import OffboardError, PositionNedYaw

from .trajectory import TrajectoryPoint, VehicleState


class PX4OffboardAdapter:
    """Translate project trajectory points to MAVSDK offboard commands."""

    def __init__(self, connection_url: str = "udpin://0.0.0.0:14540") -> None:
        self.connection_url = connection_url
        self._drone = System()
        self._state = VehicleState(0.0, 0.0, 0.0)
        self._position_ready = asyncio.Event()
        self._attitude_ready = asyncio.Event()
        self._angular_velocity_ready = asyncio.Event()
        self._flight_mode_ready = asyncio.Event()
        self._armed_ready = asyncio.Event()
        self._tasks: list[asyncio.Task[None]] = []

    async def connect(self, timeout_s: float = 30.0) -> None:
        await self._drone.connect(system_address=self.connection_url)

        async def wait_connected() -> None:
            async for state in self._drone.core.connection_state():
                if state.is_connected:
                    return

        await asyncio.wait_for(wait_connected(), timeout=timeout_s)

    async def wait_until_ready(self, timeout_s: float = 30.0) -> None:
        async def wait_health() -> None:
            async for health in self._drone.telemetry.health():
                if health.is_local_position_ok and health.is_home_position_ok:
                    return

        await asyncio.wait_for(wait_health(), timeout=timeout_s)
        self._tasks = [
            asyncio.create_task(self._watch_position()),
            asyncio.create_task(self._watch_attitude()),
            asyncio.create_task(self._watch_angular_velocity()),
            asyncio.create_task(self._watch_flight_mode()),
            asyncio.create_task(self._watch_armed()),
        ]
        await asyncio.wait_for(
            asyncio.gather(
                self._position_ready.wait(),
                self._attitude_ready.wait(),
                self._angular_velocity_ready.wait(),
                self._flight_mode_ready.wait(),
                self._armed_ready.wait(),
            ),
            timeout=timeout_s,
        )

    def state(self) -> VehicleState:
        return self._state

    async def arm(self) -> None:
        await self._drone.action.arm()

    async def action_takeoff(self, altitude_m: float) -> None:
        """Use PX4's action takeoff only as runner setup for an airborne test."""

        await self._drone.action.set_takeoff_altitude(altitude_m)
        await self._drone.action.takeoff()

    async def send(self, point: TrajectoryPoint) -> None:
        await self._drone.offboard.set_position_ned(
            PositionNedYaw(
                point.north_m,
                point.east_m,
                point.down_m,
                math.degrees(point.yaw_rad),
            )
        )

    async def start_offboard(self) -> None:
        await self._drone.offboard.start()

    async def stop_offboard(self) -> None:
        try:
            await self._drone.offboard.stop()
        except OffboardError:
            pass

    async def land(self) -> None:
        await self._drone.action.land()

    async def wait_until_disarmed(self, timeout_s: float = 30.0) -> None:
        async def wait_disarmed() -> None:
            async for armed in self._drone.telemetry.armed():
                if not armed:
                    return

        await asyncio.wait_for(wait_disarmed(), timeout=timeout_s)

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        try:
            for task in self._tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        finally:
            self._tasks.clear()
            # MAVSDK Python has no public close method for its embedded server.
            # Stop the process it created so UDP 14540 is reusable by another run.
            self._drone._stop_mavsdk_server()

    def _replace(self, **changes: Any) -> None:
        values = self._state.__dict__ | changes
        self._state = VehicleState(**values)

    async def _watch_position(self) -> None:
        async for value in self._drone.telemetry.position_velocity_ned():
            self._replace(
                north_m=value.position.north_m,
                east_m=value.position.east_m,
                down_m=value.position.down_m,
                north_m_s=value.velocity.north_m_s,
                east_m_s=value.velocity.east_m_s,
                down_m_s=value.velocity.down_m_s,
            )
            self._position_ready.set()

    async def _watch_attitude(self) -> None:
        async for value in self._drone.telemetry.attitude_euler():
            self._replace(yaw_rad=math.radians(value.yaw_deg))
            self._attitude_ready.set()

    async def _watch_angular_velocity(self) -> None:
        async for value in self._drone.telemetry.attitude_angular_velocity_body():
            self._replace(yaw_rate_rad_s=value.yaw_rad_s)
            self._angular_velocity_ready.set()

    async def _watch_flight_mode(self) -> None:
        async for value in self._drone.telemetry.flight_mode():
            mode = value.name if hasattr(value, "name") else str(value)
            self._replace(flight_mode=mode)
            self._flight_mode_ready.set()

    async def _watch_armed(self) -> None:
        async for value in self._drone.telemetry.armed():
            self._replace(armed=value)
            self._armed_ready.set()
