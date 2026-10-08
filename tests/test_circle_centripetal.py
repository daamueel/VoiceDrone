import math

import pytest

from flight.circle_centripetal import CircleCentripetal
from flight.trajectory import VehicleState


REFERENCE = VehicleState(
    north_m=12.0,
    east_m=-3.0,
    down_m=-5.0,
    yaw_rad=0.7,
)


def wrapped_difference(first: float, second: float) -> float:
    return math.atan2(math.sin(first - second), math.cos(first - second))


def test_center_is_the_initial_vehicle_position() -> None:
    circle = CircleCentripetal(radius=5.0)

    assert circle.center(REFERENCE) == (REFERENCE.north_m, REFERENCE.east_m)


def test_entry_moves_behind_vehicle_and_keeps_head_on_center() -> None:
    circle = CircleCentripetal(radius=5.0, entry_speed=1.0)
    halfway = circle.entry_point_at(circle.entry_duration / 2.0, REFERENCE)
    center_north, center_east = circle.center(REFERENCE)
    expected_yaw = math.atan2(
        center_east - halfway.east_m,
        center_north - halfway.north_m,
    )

    assert math.hypot(
        halfway.north_m - center_north,
        halfway.east_m - center_east,
    ) == pytest.approx(2.5)
    assert wrapped_difference(halfway.yaw_rad, expected_yaw) == pytest.approx(0.0)


def test_entry_endpoint_is_on_requested_circumference() -> None:
    circle = CircleCentripetal(radius=10.0, entry_speed=2.0)
    endpoint = circle.entry_point_at(circle.entry_duration, REFERENCE)

    assert circle.entry_duration == pytest.approx(5.0)
    assert math.hypot(
        endpoint.north_m - REFERENCE.north_m,
        endpoint.east_m - REFERENCE.east_m,
    ) == pytest.approx(10.0)
    assert endpoint.north_m_s == 0.0
    assert endpoint.east_m_s == 0.0


def test_entry_to_circle_has_no_position_or_yaw_jump() -> None:
    behavior = CircleCentripetal(radius=10.0, angular_velocity=0.1)
    endpoint = behavior.entry_point_at(behavior.entry_duration, REFERENCE)
    circumference_reference = behavior.circumference_reference(REFERENCE)
    circle = behavior.circle_segment(REFERENCE)
    first = circle.point_at(0.0, circumference_reference)

    assert first.north_m == pytest.approx(endpoint.north_m)
    assert first.east_m == pytest.approx(endpoint.east_m)
    assert first.down_m == pytest.approx(endpoint.down_m)
    assert wrapped_difference(first.yaw_rad, endpoint.yaw_rad) == pytest.approx(0.0)
    assert circle.center(circumference_reference) == pytest.approx(
        behavior.center(REFERENCE)
    )


@pytest.mark.parametrize("angular_velocity", [0.2, -0.2])
@pytest.mark.parametrize("fraction", [0.0, 0.25, 0.5, 0.75])
def test_circular_segment_always_faces_original_center(
    angular_velocity: float, fraction: float
) -> None:
    behavior = CircleCentripetal(radius=5.0, angular_velocity=angular_velocity)
    reference = behavior.circumference_reference(REFERENCE)
    circle = behavior.circle_segment(REFERENCE)
    point = circle.point_at(circle.duration * fraction, reference)
    center_north, center_east = behavior.center(REFERENCE)
    expected_yaw = math.atan2(
        center_east - point.east_m,
        center_north - point.north_m,
    )

    assert wrapped_difference(point.yaw_rad, expected_yaw) == pytest.approx(0.0)


def test_entry_completion_and_clamping() -> None:
    circle = CircleCentripetal(radius=5.0, entry_speed=2.0)

    assert not circle.is_entry_complete(2.499)
    assert circle.is_entry_complete(2.5)
    assert circle.entry_point_at(20.0, REFERENCE) == circle.entry_point_at(
        2.5, REFERENCE
    )


def test_return_retraces_entry_and_ends_at_original_center() -> None:
    behavior = CircleCentripetal(radius=5.0, entry_speed=2.0)
    entry_endpoint = behavior.entry_point_at(behavior.entry_duration, REFERENCE)
    return_start = behavior.return_point_at(0.0, REFERENCE)
    halfway = behavior.return_point_at(behavior.return_duration / 2.0, REFERENCE)
    return_endpoint = behavior.return_point_at(behavior.return_duration, REFERENCE)

    assert return_start.north_m == pytest.approx(entry_endpoint.north_m)
    assert return_start.east_m == pytest.approx(entry_endpoint.east_m)
    assert math.hypot(
        halfway.north_m - REFERENCE.north_m,
        halfway.east_m - REFERENCE.east_m,
    ) == pytest.approx(2.5)
    assert return_endpoint.north_m == pytest.approx(REFERENCE.north_m)
    assert return_endpoint.east_m == pytest.approx(REFERENCE.east_m)
    assert return_endpoint.north_m_s == 0.0
    assert return_endpoint.east_m_s == 0.0


def test_circle_endpoint_to_return_has_no_position_or_yaw_jump() -> None:
    behavior = CircleCentripetal(radius=5.0, angular_velocity=0.2)
    circumference = behavior.circumference_reference(REFERENCE)
    circle_endpoint = behavior.circle_segment(REFERENCE).point_at(
        behavior.duration, circumference
    )
    return_start = behavior.return_point_at(0.0, REFERENCE)

    assert return_start.north_m == pytest.approx(circle_endpoint.north_m)
    assert return_start.east_m == pytest.approx(circle_endpoint.east_m)
    assert wrapped_difference(
        return_start.yaw_rad, circle_endpoint.yaw_rad
    ) == pytest.approx(0.0)


def test_return_completion_and_clamping() -> None:
    behavior = CircleCentripetal(radius=5.0, entry_speed=2.0)

    assert not behavior.is_return_complete(2.499)
    assert behavior.is_return_complete(2.5)
    assert behavior.return_point_at(20.0, REFERENCE) == behavior.return_point_at(
        2.5, REFERENCE
    )


@pytest.mark.parametrize("entry_speed", [0.0, -1.0, math.inf, math.nan])
def test_invalid_entry_speed_is_rejected(entry_speed: float) -> None:
    with pytest.raises(ValueError):
        CircleCentripetal(entry_speed=entry_speed)


def test_nonfinite_entry_time_is_rejected() -> None:
    circle = CircleCentripetal()

    with pytest.raises(ValueError):
        circle.entry_point_at(math.nan, REFERENCE)
    with pytest.raises(ValueError):
        circle.is_entry_complete(math.inf)
    with pytest.raises(ValueError):
        circle.return_point_at(math.nan, REFERENCE)
    with pytest.raises(ValueError):
        circle.is_return_complete(math.inf)
