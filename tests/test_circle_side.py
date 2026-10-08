import math

import pytest

from flight.circle_side import CircleSide
from flight.trajectory import VehicleState


REFERENCE = VehicleState(
    north_m=12.0,
    east_m=-3.0,
    down_m=-5.0,
    yaw_rad=0.7,
)


def heading_error(point: object, center: tuple[float, float]) -> float:
    expected = math.atan2(
        center[1] - point.east_m,
        center[0] - point.north_m,
    )
    return math.atan2(
        math.sin(point.yaw_rad - expected),
        math.cos(point.yaw_rad - expected),
    )


def test_radius_only_defaults_to_one_metre_per_second_and_one_revolution() -> None:
    circle = CircleSide(radius=5.0)

    assert circle.speed == pytest.approx(1.0)
    assert circle.angular_velocity == pytest.approx(0.2)
    assert circle.duration == pytest.approx(10.0 * math.pi)


def test_first_point_is_exactly_the_airborne_reference() -> None:
    circle = CircleSide(radius=10.0, phase=0.8)

    first = circle.point_at(0.0, REFERENCE)

    assert first.north_m == pytest.approx(REFERENCE.north_m)
    assert first.east_m == pytest.approx(REFERENCE.east_m)
    assert first.down_m == REFERENCE.down_m


@pytest.mark.parametrize("angular_velocity", [0.2, -0.2])
@pytest.mark.parametrize("fraction", [0.0, 0.125, 0.25, 0.5, 0.875])
def test_head_always_faces_center(
    angular_velocity: float, fraction: float
) -> None:
    circle = CircleSide(radius=5.0, angular_velocity=angular_velocity, phase=0.4)
    point = circle.point_at(circle.duration * fraction, REFERENCE)

    assert heading_error(point, circle.center(REFERENCE)) == pytest.approx(0.0)
    assert point.yaw_rate_rad_s == pytest.approx(angular_velocity)


def test_positive_angular_velocity_is_clockwise_from_above() -> None:
    circle = CircleSide(radius=5.0, angular_velocity=0.5)
    quarter_turn_time = (math.pi / 2.0) / circle.angular_velocity

    center_north, center_east = circle.center(REFERENCE)
    point = circle.point_at(quarter_turn_time, REFERENCE)

    assert point.north_m == pytest.approx(center_north)
    assert point.east_m == pytest.approx(center_east + circle.radius)


def test_negative_angular_velocity_is_counterclockwise_from_above() -> None:
    circle = CircleSide(radius=5.0, angular_velocity=-0.5)
    quarter_turn_time = (math.pi / 2.0) / abs(circle.angular_velocity)

    center_north, center_east = circle.center(REFERENCE)
    point = circle.point_at(quarter_turn_time, REFERENCE)

    assert point.north_m == pytest.approx(center_north)
    assert point.east_m == pytest.approx(center_east - circle.radius)


def test_equations_respect_explicit_phase() -> None:
    circle = CircleSide(radius=4.0, angular_velocity=0.25, phase=math.pi / 3.0)
    trajectory_time = 2.0
    theta = circle.phase + circle.angular_velocity * trajectory_time
    center_north, center_east = circle.center(REFERENCE)

    point = circle.point_at(trajectory_time, REFERENCE)

    assert point.north_m == pytest.approx(
        center_north + circle.radius * math.cos(theta)
    )
    assert point.east_m == pytest.approx(
        center_east + circle.radius * math.sin(theta)
    )


@pytest.mark.parametrize("angular_velocity", [0.2, -0.2])
def test_tangential_speed_matches_radius_times_angular_speed(
    angular_velocity: float,
) -> None:
    circle = CircleSide(radius=5.0, angular_velocity=angular_velocity)
    point = circle.point_at(3.0, REFERENCE)

    speed = math.hypot(point.north_m_s, point.east_m_s)
    assert speed == pytest.approx(1.0)


def test_position_and_yaw_are_continuous_at_start_and_end() -> None:
    circle = CircleSide(radius=10.0, angular_velocity=0.1)
    epsilon = 1e-6

    start = circle.point_at(0.0, REFERENCE)
    just_after_start = circle.point_at(epsilon, REFERENCE)
    just_before_end = circle.point_at(circle.duration - epsilon, REFERENCE)
    end = circle.point_at(circle.duration, REFERENCE)

    assert math.hypot(
        just_after_start.north_m - start.north_m,
        just_after_start.east_m - start.east_m,
    ) == pytest.approx(circle.speed * epsilon, rel=1e-6)
    assert math.hypot(
        end.north_m - just_before_end.north_m,
        end.east_m - just_before_end.east_m,
    ) == pytest.approx(circle.speed * epsilon, rel=1e-6)
    assert end.north_m == pytest.approx(start.north_m)
    assert end.east_m == pytest.approx(start.east_m)
    assert end.yaw_rad == pytest.approx(start.yaw_rad)


def test_completion_and_explicit_duration() -> None:
    circle = CircleSide(radius=5.0, angular_velocity=0.2, duration=7.5)

    assert not circle.is_complete(7.499)
    assert circle.is_complete(7.5)
    assert circle.point_at(20.0, REFERENCE) == circle.point_at(7.5, REFERENCE)


def test_consistent_explicit_speed_and_angular_velocity_are_allowed() -> None:
    circle = CircleSide(radius=10.0, speed=1.0, angular_velocity=0.1)

    assert circle.speed == pytest.approx(1.0)
    assert circle.duration == pytest.approx(20.0 * math.pi)


def test_conflicting_speed_and_angular_velocity_are_rejected() -> None:
    with pytest.raises(ValueError, match="conflicts"):
        CircleSide(radius=10.0, speed=2.0, angular_velocity=0.1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"radius": 0.0},
        {"radius": -1.0},
        {"radius": math.inf},
        {"speed": 0.0},
        {"speed": -1.0},
        {"angular_velocity": 0.0},
        {"angular_velocity": math.nan},
        {"duration": 0.0},
        {"duration": -1.0},
        {"phase": math.inf},
    ],
)
def test_invalid_parameters_are_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(ValueError):
        CircleSide(**kwargs)


def test_nonfinite_trajectory_time_is_rejected() -> None:
    circle = CircleSide()

    with pytest.raises(ValueError):
        circle.point_at(math.nan, REFERENCE)
    with pytest.raises(ValueError):
        circle.is_complete(math.inf)
