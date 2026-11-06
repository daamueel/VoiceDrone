import math

import pytest

from control.commands import (
    CircleBehavior,
    CircleCommand,
    Direction,
    ExitCommand,
    HelpCommand,
    LandCommand,
    StatusCommand,
    TakeoffCommand,
)
from control.parser import CommandParseError, parse_command


@pytest.mark.parametrize(
    ("text", "altitude"),
    [
        ("takeoff", 0.5),
        ("TAKEOFF!", 0.5),
        ("takeoff 5", 5.0),
        ("take off to 5 meters", 5.0),
        ("Take off to five metres.", 5.0),
        ("takeoff one point five meter", 1.5),
        ("take off to twenty-five meters", 25.0),
        ("takeoff one hundred and five metres", 105.0),
    ],
)
def test_parse_takeoff(text: str, altitude: float) -> None:
    assert parse_command(text) == TakeoffCommand(altitude)


@pytest.mark.parametrize(
    ("text", "behavior", "direction", "radius"),
    [
        ("circle", CircleBehavior.CENTRIPETAL, Direction.CLOCKWISE, 0.5),
        ("circle radius 5", CircleBehavior.CENTRIPETAL, Direction.CLOCKWISE, 5.0),
        (
            "clockwise circle radius 5",
            CircleBehavior.CENTRIPETAL,
            Direction.CLOCKWISE,
            5.0,
        ),
        (
            "counterclockwise circle radius 5",
            CircleBehavior.CENTRIPETAL,
            Direction.COUNTERCLOCKWISE,
            5.0,
        ),
        (
            "counter-clockwise circle radius five metres",
            CircleBehavior.CENTRIPETAL,
            Direction.COUNTERCLOCKWISE,
            5.0,
        ),
        ("centripetal radius 5", CircleBehavior.CENTRIPETAL, Direction.CLOCKWISE, 5.0),
        (
            "fixed yaw circle radius 5",
            CircleBehavior.FIXED_YAW,
            Direction.CLOCKWISE,
            5.0,
        ),
        ("circle side radius 5", CircleBehavior.SIDE, Direction.CLOCKWISE, 5.0),
        (
            "Circle side, radius one point five meters!",
            CircleBehavior.SIDE,
            Direction.CLOCKWISE,
            1.5,
        ),
    ],
)
def test_parse_circle(
    text: str,
    behavior: CircleBehavior,
    direction: Direction,
    radius: float,
) -> None:
    assert parse_command(text) == CircleCommand(behavior, radius, direction)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("land", LandCommand()),
        ("Status?", StatusCommand()),
        ("help!", HelpCommand()),
        ("EXIT.", ExitCommand()),
    ],
)
def test_parse_non_parameterized_commands(text: str, expected: object) -> None:
    assert parse_command(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "fly",
        "land now",
        "takeoff altitude 5",
        "takeoff 5 6",
        "takeoff nan",
        "takeoff inf",
        "takeoff 1e309",
        "takeoff -5",
        "takeoff 0",
        "takeoff 121",
        "circle 5",
        "circle diameter 5",
        "circle radius",
        "circle radius 5 6",
        "circle radius nan",
        "circle radius -5",
        "circle radius 1001",
        "circle circle",
        "clockwise clockwise circle",
        "clockwise counterclockwise circle",
        "fixed yaw centripetal circle",
        "circle side centripetal",
        "side radius 5",
        "fixed yaw radius 5",
        "status circle",
    ],
)
def test_reject_ambiguous_conflicting_or_unsupported_input(text: str) -> None:
    with pytest.raises(CommandParseError):
        parse_command(text)


def test_circle_effective_values_are_derived_after_parsing() -> None:
    command = parse_command("counterclockwise fixed yaw circle radius 4")

    assert isinstance(command, CircleCommand)
    assert command.speed_m_s == pytest.approx(1.0)
    assert command.angular_velocity_rad_s == pytest.approx(-0.25)
    assert command.duration_s == pytest.approx(8.0 * math.pi)
