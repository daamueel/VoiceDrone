"""Interactive keyboard controller for dry-run and PX4 SITL."""

import argparse
import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import sys

from .commands import (
    CircleCommand,
    Command,
    ExitCommand,
    HelpCommand,
    LandCommand,
    StatusCommand,
    TakeoffCommand,
)
from .parser import CommandParseError, parse_command


HELP_TEXT = """Supported commands:
  takeoff
  takeoff 5
  take off to 5 meters
  circle
  circle radius 5
  five-meter circle (5 m diameter, 2.5 m radius)
  circle five meters wide (5 m diameter, 2.5 m radius)
  clockwise circle radius 5
  counterclockwise circle radius 5
  centripetal radius 5
  fixed yaw circle radius 5
  circle side radius 5
  land
  status
  help
  exit
In PX4 SITL, press L during an active maneuver to land immediately."""


class FlightState(str, Enum):
    LANDED = "landed"
    AIRBORNE = "airborne"


@dataclass(frozen=True, slots=True)
class DryRunResult:
    action: str
    completion: str | None = None
    rejected: bool = False
    exit_requested: bool = False


def command_name(command: Command) -> str:
    if isinstance(command, TakeoffCommand):
        return "takeoff"
    if isinstance(command, CircleCommand):
        return "circle"
    if isinstance(command, LandCommand):
        return "land"
    if isinstance(command, StatusCommand):
        return "status"
    if isinstance(command, HelpCommand):
        return "help"
    return "exit"


def effective_parameters(command: Command) -> str:
    """Return all values that would affect execution of a command."""

    if isinstance(command, TakeoffCommand):
        return f"altitude={command.altitude_m:.3f} m"
    if isinstance(command, CircleCommand):
        return (
            f"behavior={command.behavior.value}, "
            f"direction={command.direction.value}, "
            f"radius={command.radius_m:.3f} m, "
            f"speed={command.speed_m_s:.3f} m/s, "
            f"angular_velocity={command.angular_velocity_rad_s:.6f} rad/s, "
            f"duration={command.duration_s:.3f} s"
        )
    return "none"


class DryRunController:
    """Validate command order while performing no external flight actions."""

    def __init__(self) -> None:
        self.state = FlightState.LANDED

    def execute(self, command: Command) -> DryRunResult:
        if isinstance(command, TakeoffCommand):
            if self.state is FlightState.AIRBORNE:
                return DryRunResult(
                    "takeoff is unavailable while already airborne",
                    rejected=True,
                )
            self.state = FlightState.AIRBORNE
            return DryRunResult(
                f"simulate takeoff to {command.altitude_m:.3f} m",
                "simulated state is airborne; no PX4 action was sent",
            )

        if isinstance(command, CircleCommand):
            if self.state is FlightState.LANDED:
                return DryRunResult(
                    "circle is unavailable while landed",
                    rejected=True,
                )
            return DryRunResult(
                "simulate complete circle and return to its airborne start",
                "simulated state remains airborne; no PX4 action was sent",
            )

        if isinstance(command, LandCommand):
            if self.state is FlightState.LANDED:
                return DryRunResult(
                    "land is unavailable while already landed",
                    rejected=True,
                )
            self.state = FlightState.LANDED
            return DryRunResult(
                "simulate landing and disarm",
                "simulated state is landed; no PX4 action was sent",
            )

        if isinstance(command, StatusCommand):
            return DryRunResult(f"dry-run flight state is {self.state.value}")
        if isinstance(command, HelpCommand):
            return DryRunResult(HELP_TEXT)
        if isinstance(command, ExitCommand):
            return DryRunResult(
                "exit dry-run controller",
                "controller closed; no PX4 connection was opened",
                exit_requested=True,
            )
        raise TypeError(f"unsupported structured command: {type(command).__name__}")


def run_keyboard(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Run an interactive dry-run loop and return a process exit code."""

    controller = DryRunController()
    output_fn("VoiceDrone keyboard control - DRY RUN")
    output_fn("No PX4 connection will be opened and no flight action will be sent.")
    output_fn("Type 'help' for commands or 'exit' to close.")

    while True:
        try:
            text = input_fn("voicedrone> ")
        except EOFError:
            output_fn("Controller closed: end of input; no PX4 connection was opened.")
            return 0
        except KeyboardInterrupt:
            output_fn("\nController cancelled; no PX4 connection was opened.")
            return 130

        try:
            command = parse_command(text)
        except CommandParseError as error:
            output_fn(f"Rejected: {error}")
            continue

        output_fn(f"Parsed command: {command_name(command)}")
        output_fn(f"Effective parameters: {effective_parameters(command)}")
        result = controller.execute(command)
        if result.rejected:
            output_fn(f"Rejected: {result.action}; no flight action was taken.")
        else:
            output_fn(f"Action: {result.action}")
            if result.completion is not None:
                output_fn(f"Complete: {result.completion}.")
        if result.exit_requested:
            return 0


async def run_sitl_keyboard(
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """Run typed commands on one connected SITL flight session."""

    from .session import CommandRejected, FlightSession

    output_fn("VoiceDrone keyboard control - PX4 SITL")
    async with FlightSession() as session:
        output_fn(f"Telemetry CSV: {session.log.path}")
        output_fn(f"Command record: {session.record_path}")
        output_fn("Type 'help' for commands or 'exit' to land and close.")
        output_fn("During a maneuver, press L without Enter to land immediately.")
        while True:
            try:
                text = await _read_sitl_input(input_fn, "voicedrone> ")
            except EOFError:
                output_fn("End of input; closing session.")
                return 0
            except KeyboardInterrupt:
                output_fn("Cancelled; closing session and landing if airborne.")
                return 130

            try:
                command = parse_command(text)
            except CommandParseError as error:
                output_fn(f"Rejected: {error}")
                session.record_rejection(text, str(error))
                continue

            output_fn(f"Parsed command: {command_name(command)}")
            output_fn(f"Effective parameters: {effective_parameters(command)}")
            try:
                if isinstance(command, (TakeoffCommand, CircleCommand)):
                    result = await execute_with_land_hotkey(
                        session, command, output_fn=output_fn
                    )
                else:
                    result = await session.execute(command)
            except CommandRejected as error:
                output_fn(f"Rejected: {error}; no flight action was taken.")
                continue
            output_fn(f"Complete: {result.message}")
            if result.exit_requested:
                return 0


async def _read_sitl_input(
    input_fn: Callable[[str], str], prompt: str, *, clear_pending: bool = False
) -> str:
    """Keep console input cancellable when the MAVSDK link is lost."""

    if input_fn is not input or sys.platform != "win32" or not sys.stdin.isatty():
        return await asyncio.to_thread(input_fn, prompt)

    import msvcrt

    if clear_pending:
        while msvcrt.kbhit():
            msvcrt.getwch()

    sys.stdout.write(prompt)
    sys.stdout.flush()
    characters: list[str] = []
    while True:
        if msvcrt.kbhit():
            key = msvcrt.getwch()
            if key in ("\r", "\n"):
                sys.stdout.write("\n")
                sys.stdout.flush()
                return "".join(characters)
            if key == "\b":
                if characters:
                    characters.pop()
                    sys.stdout.write("\b \b")
                    sys.stdout.flush()
            elif key in ("\x00", "\xe0"):
                msvcrt.getwch()
            elif key.isprintable():
                characters.append(key)
                sys.stdout.write(key)
                sys.stdout.flush()
        await asyncio.sleep(0.05)


def _console_key() -> str | None:
    """Poll a Windows console without blocking the active flight coroutine."""

    if sys.platform != "win32" or not sys.stdin.isatty():
        return None
    import msvcrt

    if msvcrt.kbhit():
        return msvcrt.getwch()
    return None


async def execute_with_land_hotkey(
    session: object,
    command: TakeoffCommand | CircleCommand,
    *,
    output_fn: Callable[[str], None] = print,
    key_fn: Callable[[], str | None] = _console_key,
):
    """Let L interrupt an active trajectory and invoke session landing."""

    flight = asyncio.create_task(session.execute(command))
    try:
        while not flight.done():
            key = key_fn()
            if key is not None and key.casefold() == "l":
                output_fn("Immediate land requested; stopping active maneuver.")
                if hasattr(session, "record_immediate_land"):
                    session.record_immediate_land()
                flight.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await flight
                result = await session.execute(LandCommand())
                return result
            await asyncio.sleep(0.05)
        return await flight
    except BaseException:
        if not flight.done():
            flight.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await flight
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--sitl", action="store_true", help="connect to PX4 SITL at UDP 14540"
    )
    args = parser.parse_args()
    try:
        status = asyncio.run(run_sitl_keyboard()) if args.sitl else run_keyboard()
    except asyncio.CancelledError as error:
        print(f"SITL session interrupted: {error}")
        print("Landing and disarm could not be confirmed. Check PX4 SITL status.")
        status = 1
    except Exception as error:
        print(f"{'SITL session' if args.sitl else 'Keyboard control'} failed: {error}")
        if args.sitl:
            print("Check PX4 SITL status before another flight.")
        status = 1
    except KeyboardInterrupt:
        print("Cancelled")
        status = 130
    sys.exit(status)


if __name__ == "__main__":
    main()
