import asyncio
from collections.abc import Iterator
import sys

import pytest

from control.commands import CircleCommand, TakeoffCommand
from control.run_keyboard import (
    DryRunController,
    FlightState,
    effective_parameters,
    execute_with_land_hotkey,
    _read_sitl_input,
    run_keyboard,
)


def scripted_input(lines: list[str]) -> tuple[Iterator[str], object]:
    iterator = iter(lines)

    def read(_: str) -> str:
        return next(iterator)

    return iterator, read


def test_effective_parameters_show_permanent_user_defaults() -> None:
    assert effective_parameters(TakeoffCommand()) == "altitude=0.500 m"
    assert effective_parameters(CircleCommand()) == (
        "behavior=circle_centripetal, direction=clockwise, radius=0.500 m, "
        "speed=1.000 m/s, angular_velocity=2.000000 rad/s, duration=3.142 s"
    )


def test_dry_run_controller_enforces_flight_state() -> None:
    controller = DryRunController()

    assert controller.execute(CircleCommand()).rejected
    assert controller.state is FlightState.LANDED
    assert not controller.execute(TakeoffCommand()).rejected
    assert controller.state is FlightState.AIRBORNE
    assert controller.execute(TakeoffCommand()).rejected
    assert not controller.execute(CircleCommand()).rejected


def test_keyboard_sequence_previews_commands_without_px4() -> None:
    _, read = scripted_input(
        [
            "circle",
            "takeoff",
            "takeoff 5",
            "fixed yaw circle radius 4",
            "land",
            "land",
            "status",
            "help",
            "exit",
        ]
    )
    output: list[str] = []

    exit_code = run_keyboard(input_fn=read, output_fn=output.append)
    joined = "\n".join(output)

    assert exit_code == 0
    assert "No PX4 connection will be opened" in joined
    assert "behavior=circle, direction=clockwise, radius=4.000 m" in joined
    assert "circle is unavailable while landed" in joined
    assert "takeoff is unavailable while already airborne" in joined
    assert "land is unavailable while already landed" in joined
    assert "dry-run flight state is landed" in joined
    assert "Supported commands:" in joined
    assert joined.count("no PX4 action was sent") == 3


def test_rejected_text_does_not_change_dry_run_state() -> None:
    _, read = scripted_input(["takeoff maybe", "status", "exit"])
    output: list[str] = []

    run_keyboard(input_fn=read, output_fn=output.append)
    joined = "\n".join(output)

    assert "Rejected: invalid spoken number" in joined
    assert "dry-run flight state is landed" in joined


def test_end_of_input_closes_cleanly() -> None:
    def end_of_input(_: str) -> str:
        raise EOFError

    output: list[str] = []
    assert run_keyboard(input_fn=end_of_input, output_fn=output.append) == 0
    assert "end of input" in output[-1]


def test_keyboard_interrupt_returns_standard_exit_code() -> None:
    def interrupt(_: str) -> str:
        raise KeyboardInterrupt

    output: list[str] = []
    assert run_keyboard(input_fn=interrupt, output_fn=output.append) == 130
    assert "cancelled" in output[-1]


def test_controller_rejects_unknown_structured_type() -> None:
    with pytest.raises(TypeError, match="unsupported structured command"):
        DryRunController().execute(object())  # type: ignore[arg-type]


def test_immediate_land_preempts_active_maneuver() -> None:
    from control.session import FlightResult
    from control.commands import LandCommand

    class FakeSession:
        def __init__(self) -> None:
            self.cancelled = False
            self.landed = False
            self.emergency_recorded = False

        def record_immediate_land(self) -> None:
            self.emergency_recorded = True

        async def execute(self, command):
            if isinstance(command, LandCommand):
                self.landed = True
                return FlightResult("landing complete")
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                self.cancelled = True
                raise

    session = FakeSession()
    keys = iter((None, "l"))
    output: list[str] = []
    result = asyncio.run(
        execute_with_land_hotkey(
            session, CircleCommand(), output_fn=output.append,
            key_fn=lambda: next(keys),
        )
    )

    assert session.cancelled
    assert session.landed
    assert session.emergency_recorded
    assert result.message == "landing complete"
    assert "Immediate land requested" in output[0]


def test_console_input_can_be_cancelled_on_connection_loss(monkeypatch) -> None:
    class ConsoleInput:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", ConsoleInput())
    monkeypatch.setattr(sys, "platform", "win32")
    import msvcrt

    monkeypatch.setattr(msvcrt, "kbhit", lambda: False)

    async def scenario() -> None:
        reading = asyncio.create_task(_read_sitl_input(input, "test> "))
        await asyncio.sleep(0.1)
        reading.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(reading, 1.0)

    asyncio.run(scenario())


def test_confirmation_ignores_keys_typed_before_preview(monkeypatch) -> None:
    class ConsoleInput:
        def isatty(self) -> bool:
            return True

    monkeypatch.setattr(sys, "stdin", ConsoleInput())
    monkeypatch.setattr(sys, "platform", "win32")
    import msvcrt

    pending = list("YES\r")
    monkeypatch.setattr(msvcrt, "kbhit", lambda: bool(pending))
    monkeypatch.setattr(msvcrt, "getwch", lambda: pending.pop(0))

    async def scenario() -> str:
        reading = asyncio.create_task(
            _read_sitl_input(input, "confirm> ", clear_pending=True)
        )
        await asyncio.sleep(0.1)
        pending.extend("no\r")
        return await asyncio.wait_for(reading, 1.0)

    assert asyncio.run(scenario()) == "no"
