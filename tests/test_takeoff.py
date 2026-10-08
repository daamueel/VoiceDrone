import math

import pytest

from flight.takeoff import Takeoff
from flight.trajectory import VehicleState


REFERENCE = VehicleState(north_m=12.0, east_m=-3.0, down_m=2.0, yaw_rad=0.7)


def test_takeoff_climbs_using_negative_ned_down() -> None:
    takeoff = Takeoff(target_altitude=5.0, ascent_speed=1.0)

    start = takeoff.point_at(0.0, REFERENCE)
    halfway = takeoff.point_at(2.5, REFERENCE)
    target = takeoff.point_at(5.0, REFERENCE)

    assert start.down_m == pytest.approx(2.0)
    assert halfway.down_m == pytest.approx(-0.5)
    assert halfway.down_m_s == pytest.approx(-1.0)
    assert target.down_m == pytest.approx(-3.0)
    assert target.down_m_s == pytest.approx(0.0)


def test_takeoff_holds_starting_horizontal_position_and_yaw() -> None:
    point = Takeoff().point_at(3.0, REFERENCE)

    assert point.north_m == REFERENCE.north_m
    assert point.east_m == REFERENCE.east_m
    assert point.yaw_rad == REFERENCE.yaw_rad
    assert point.north_m_s == 0.0
    assert point.east_m_s == 0.0
    assert point.yaw_rate_rad_s == 0.0


def test_takeoff_clamps_time_before_start_and_after_completion() -> None:
    takeoff = Takeoff(target_altitude=5.0, ascent_speed=2.0)

    assert takeoff.point_at(-1.0, REFERENCE).down_m == REFERENCE.down_m
    assert takeoff.point_at(20.0, REFERENCE).down_m == pytest.approx(-3.0)
    assert takeoff.duration == pytest.approx(2.5)


def test_takeoff_completion_uses_measured_down_and_tolerance() -> None:
    takeoff = Takeoff(target_altitude=5.0, position_tolerance=0.25)

    assert not takeoff.is_complete(
        REFERENCE, VehicleState(12.0, -3.0, down_m=-2.70)
    )
    assert takeoff.is_complete(
        REFERENCE, VehicleState(12.0, -3.0, down_m=-2.76)
    )
    assert takeoff.is_complete(
        REFERENCE, VehicleState(12.0, -3.0, down_m=-3.25)
    )
    assert not takeoff.is_complete(
        REFERENCE, VehicleState(12.0, -3.0, down_m=-3.26)
    )


def test_takeoff_settled_requires_low_vertical_speed_and_valid_position() -> None:
    takeoff = Takeoff(
        target_altitude=5.0,
        position_tolerance=0.25,
        vertical_speed_tolerance=0.2,
    )

    assert takeoff.is_settled(
        REFERENCE, VehicleState(12.0, -3.0, down_m=-3.1, down_m_s=0.1)
    )
    assert not takeoff.is_settled(
        REFERENCE, VehicleState(12.0, -3.0, down_m=-3.1, down_m_s=0.21)
    )
    assert not takeoff.is_settled(
        REFERENCE, VehicleState(math.nan, -3.0, down_m=-3.1, down_m_s=0.1)
    )


@pytest.mark.parametrize(
    "keyword,value",
    [
        ("target_altitude", 0.0),
        ("target_altitude", -1.0),
        ("ascent_speed", 0.0),
        ("position_tolerance", 0.0),
        ("vertical_speed_tolerance", 0.0),
        ("target_altitude", math.inf),
    ],
)
def test_takeoff_rejects_invalid_parameters(keyword: str, value: float) -> None:
    with pytest.raises(ValueError):
        Takeoff(**{keyword: value})


def test_takeoff_rejects_nonfinite_trajectory_time() -> None:
    with pytest.raises(ValueError):
        Takeoff().point_at(math.nan, REFERENCE)
