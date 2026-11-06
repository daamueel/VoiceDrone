"""One persistent PX4 SITL connection for sequential structured commands."""

import asyncio
import contextlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import time

from flight.circle import Circle
from flight.circle_centripetal import CircleCentripetal
from flight.circle_side import CircleSide
from flight.px4_offboard_adapter import PX4OffboardAdapter
from flight.run_sitl import (
    align_circle_side_yaw,
    execute_centered_circle_behavior,
    execute_circle,
    execute_takeoff,
)
from flight.sitl_log import SitlLogger
from flight.takeoff import Takeoff
from flight.trajectory import TrajectoryPoint

from .commands import (
    CircleBehavior,
    CircleCommand,
    Command,
    ExitCommand,
    HelpCommand,
    LandCommand,
    StatusCommand,
    TakeoffCommand,
)


SITL_CONNECTION = "udpin://0.0.0.0:14540"


class CommandRejected(ValueError):
    """A valid command is incompatible with the observed flight state."""


@dataclass(frozen=True)
class FlightResult:
    message: str
    exit_requested: bool = False


class FlightSession:
    """Own the connection, telemetry log, action order, and emergency cleanup."""

    def __init__(
        self,
        *,
        adapter: PX4OffboardAdapter | None = None,
        directory: Path = Path("logs"),
        input_type: str = "keyboard",
    ) -> None:
        if input_type not in {"keyboard", "voice"}:
            raise ValueError("unsupported input type")
        self.adapter = adapter or PX4OffboardAdapter(SITL_CONNECTION)
        self.directory = directory
        self.input_type = input_type
        self.log: SitlLogger | None = None
        self.record = None
        self.record_path: Path | None = None
        self.connected = False
        self.airborne = False
        self.command: TrajectoryPoint | None = None
        self._connection_task: asyncio.Task[None] | None = None

    async def __aenter__(self) -> "FlightSession":
        self.directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.record_path = self.directory / f"control_{stamp}_{self.input_type}.jsonl"
        self.record = self.record_path.open("w", encoding="utf-8")
        self.log = SitlLogger(f"control_{stamp}", directory=self.directory)
        try:
            await self.adapter.connect()
            self.connected = True
            await self.adapter.wait_until_ready()
            if self.adapter.state().armed:
                raise RuntimeError("SITL vehicle is already armed at session start")
            self._record("connected")
            if hasattr(self.adapter, "wait_until_disconnected"):
                owner = asyncio.current_task()

                async def watch_connection() -> None:
                    await self.adapter.wait_until_disconnected()
                    self._record("disconnected")
                    if owner is not None:
                        owner.cancel("PX4 SITL connection lost")

                self._connection_task = asyncio.create_task(watch_connection())
            return self
        except BaseException:
            await self.close()
            raise

    async def __aexit__(self, *_: object) -> None:
        await self.close()

    def _record(self, event: str, **details: object) -> None:
        if self.record is not None:
            self.record.write(json.dumps({
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "event": event,
                **details,
            }, allow_nan=False) + "\n")
            self.record.flush()

    def record_rejection(self, text: str, reason: str) -> None:
        self._record("rejected", text=text, reason=reason)

    def _is_airborne(self) -> bool:
        state = self.adapter.state()
        return self.airborne or state.armed

    async def execute(self, command: Command) -> FlightResult:
        self._record("requested", command=type(command).__name__, parameters=asdict(command))
        try:
            if isinstance(command, TakeoffCommand):
                if self._is_airborne():
                    raise CommandRejected("takeoff is unavailable while already airborne")
                result = await self._takeoff(command)
            elif isinstance(command, CircleCommand):
                if not self._is_airborne():
                    raise CommandRejected("circle is unavailable while landed")
                result = await self._circle(command)
            elif isinstance(command, LandCommand):
                if not self._is_airborne():
                    raise CommandRejected("land is unavailable while already landed")
                await self._land()
                result = FlightResult("landing complete: vehicle disarmed")
            elif isinstance(command, StatusCommand):
                state = self.adapter.state()
                result = FlightResult(
                    f"state={'airborne' if self._is_airborne() else 'landed'}, "
                    f"armed={state.armed}, mode={state.flight_mode}, "
                    f"N/E/D=({state.north_m:.3f}, {state.east_m:.3f}, "
                    f"{state.down_m:.3f}) m"
                )
            elif isinstance(command, HelpCommand):
                from .run_keyboard import HELP_TEXT
                result = FlightResult(HELP_TEXT)
            elif isinstance(command, ExitCommand):
                result = FlightResult("exit requested", exit_requested=True)
            else:
                raise TypeError(f"unsupported command: {type(command).__name__}")
        except CommandRejected as error:
            self._record("rejected", reason=str(error))
            raise
        except BaseException as error:
            self._record("failed", error=repr(error))
            raise
        self._record("completed", message=result.message)
        return result

    async def _takeoff(self, command: TakeoffCommand) -> FlightResult:
        assert self.log is not None
        behavior = Takeoff(target_altitude=command.altitude_m)
        reference = self.adapter.state()
        self.command = behavior.point_at(0.0, reference)
        await self.adapter.send(self.command)
        await self.adapter.arm()
        self.airborne = True
        await self.adapter.start_offboard()
        self.command = await execute_takeoff(
            self.adapter, self.log, behavior, reference, 1.0, 15.0
        )
        return FlightResult(f"takeoff settled at {command.altitude_m:.3f} m")

    async def _circle(self, command: CircleCommand) -> FlightResult:
        assert self.log is not None
        options = dict(
            radius=command.radius_m,
            speed=command.speed_m_s,
            angular_velocity=command.angular_velocity_rad_s,
        )
        reference = self.adapter.state()
        if command.behavior is CircleBehavior.SIDE:
            behavior = CircleSide(**options)
            self.command = behavior.point_at(0.0, reference)
            await self.adapter.send(self.command)
            await align_circle_side_yaw(self.adapter, self.log, self.command)
            self.command = await execute_circle(
                self.adapter, self.log, behavior, reference, "Side circle", 15.0
            )
        else:
            cls = (
                CircleCentripetal
                if command.behavior is CircleBehavior.CENTRIPETAL
                else Circle
            )
            behavior = cls(**options)
            self.command = behavior.entry_point_at(0.0, reference)
            await self.adapter.send(self.command)
            self.command = await execute_centered_circle_behavior(
                self.adapter, self.log, behavior, reference,
                command.behavior.value, 15.0, 15.0, 15.0,
            )
        return FlightResult(f"{command.behavior.value} complete; vehicle remains airborne")

    async def _land(self) -> None:
        assert self.log is not None
        await self.adapter.stop_offboard()
        await self.adapter.land()
        start = time.monotonic()
        while self.adapter.state().armed:
            if self.command is not None:
                self.log.write(time.monotonic() - start, "landing", self.command, self.adapter.state())
            if time.monotonic() - start > 30.0:
                raise TimeoutError("landing did not disarm within 30 seconds")
            await asyncio.sleep(0.1)
        await self.adapter.wait_until_disarmed(timeout_s=5.0)
        if self.command is not None:
            self.log.write(time.monotonic() - start, "landing", self.command, self.adapter.state())
        self.airborne = False

    async def close(self) -> None:
        if self._connection_task is not None:
            self._connection_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._connection_task
            self._connection_task = None
        try:
            if self.connected and self._is_airborne():
                self._record("cleanup_landing")
                landing = asyncio.create_task(self._land())
                try:
                    while not landing.done():
                        try:
                            await asyncio.shield(landing)
                        except asyncio.CancelledError:
                            # A second interrupt must not abandon a landing
                            # already in progress.
                            continue
                    await landing
                except BaseException as error:
                    self._record("cleanup_failed", error=repr(error))
                    raise
        finally:
            try:
                await self.adapter.close()
            finally:
                self.connected = False
                if self.log is not None:
                    self.log.close()
                    self.log = None
                if self.record is not None:
                    self.record.close()
                    self.record = None
