import math

import pytest

from control.commands import (
    CircleBehavior,
    CircleCommand,
    Direction,
    TakeoffCommand,
)


def test_takeoff_uses_user_facing_half_metre_default() -> None:
    assert TakeoffCommand().altitude_m == pytest.approx(0.5)


@pytest.mark.parametrize("altitude", [0.1, 120.0])
def test_takeoff_accepts_altitude_boundaries(altitude: float) -> None:
    assert TakeoffCommand(altitude).altitude_m == pytest.approx(altitude)


@pytest.mark.parametrize("altitude", [0.0, 0.099, 120.001, math.inf, math.nan])
def test_takeoff_rejects_invalid_altitude(altitude: float) -> None:
    with pytest.raises(ValueError):
        TakeoffCommand(altitude)


def test_circle_defaults_to_centered_inward_facing_behavior() -> None:
    command = CircleCommand()

    assert command.behavior is CircleBehavior.CENTRIPETAL
    assert command.radius_m == pytest.approx(0.5)
    assert command.direction is Direction.CLOCKWISE
    assert command.speed_m_s == pytest.approx(1.0)
    assert command.angular_velocity_rad_s == pytest.approx(2.0)
    assert command.duration_s == pytest.approx(math.pi)


def test_counterclockwise_circle_has_negative_angular_velocity() -> None:
    command = CircleCommand(radius_m=4.0, direction=Direction.COUNTERCLOCKWISE)

    assert command.angular_velocity_rad_s == pytest.approx(-0.25)
    assert command.duration_s == pytest.approx(8.0 * math.pi)


@pytest.mark.parametrize("radius", [0.0, 0.099, 1000.001, math.inf, math.nan])
def test_circle_rejects_invalid_radius(radius: float) -> None:
    with pytest.raises(ValueError):
        CircleCommand(radius_m=radius)
