import math

import pytest

from voicedrone.circle import Circle
from voicedrone.trajectory import VehicleState


REFERENCE = VehicleState(north_m=12.0, east_m=-3.0, down_m=-5.0, yaw_rad=0.7)


@pytest.mark.parametrize("angular_velocity", [0.2, -0.2])
@pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.75, 1.0])
def test_centered_circle_holds_starting_yaw(
    angular_velocity: float, fraction: float
) -> None:
    behavior = Circle(radius=5.0, angular_velocity=angular_velocity)
    circumference = behavior.circumference_reference(REFERENCE)
    circle = behavior.side_circle(REFERENCE)
    point = circle.point_at(circle.duration * fraction, circumference)

    assert point.yaw_rad == pytest.approx(REFERENCE.yaw_rad)
    assert point.yaw_rate_rad_s == 0.0
    assert point.down_m == REFERENCE.down_m
    assert math.hypot(
        point.north_m - REFERENCE.north_m,
        point.east_m - REFERENCE.east_m,
    ) == pytest.approx(5.0)


def test_entry_and_first_circle_point_share_position_and_yaw() -> None:
    behavior = Circle(radius=5.0)
    endpoint = behavior.entry_point_at(behavior.entry_duration, REFERENCE)
    first = behavior.side_circle(REFERENCE).point_at(
        0.0, behavior.circumference_reference(REFERENCE)
    )

    assert first.north_m == pytest.approx(endpoint.north_m)
    assert first.east_m == pytest.approx(endpoint.east_m)
    assert first.yaw_rad == pytest.approx(endpoint.yaw_rad)


def test_radius_only_uses_one_metre_per_second_and_one_revolution() -> None:
    behavior = Circle(radius=5.0)

    assert behavior.speed == pytest.approx(1.0)
    assert behavior.angular_velocity == pytest.approx(0.2)
    assert behavior.duration == pytest.approx(10.0 * math.pi)
