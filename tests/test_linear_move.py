import math

import pytest

from flight.linear_move import LinearMove
from flight.trajectory import VehicleState


def test_linear_move_interpolates_and_holds_yaw() -> None:
    reference = VehicleState(10.0, -3.0, -2.0, yaw_rad=math.pi / 2)
    move = LinearMove(0.0, 2.0, 0.0)
    halfway = move.point_at(1.0, reference)
    assert (halfway.north_m, halfway.east_m, halfway.down_m) == pytest.approx((10, -2, -2))
    assert halfway.yaw_rad == pytest.approx(math.pi / 2)
    assert move.point_at(3.0, reference).east_m == pytest.approx(-1)
    assert move.is_settled(reference, VehicleState(10, -1, -2))
    assert not move.is_settled(reference, VehicleState(10, -1.5, -2))


def test_vertical_move_uses_ned_down() -> None:
    reference = VehicleState(1, 2, -1)
    assert LinearMove(0, 0, -0.5).point_at(1, reference).down_m == pytest.approx(-1.5)
    assert LinearMove(0, 0, 0.5).point_at(1, reference).down_m == pytest.approx(-0.5)
