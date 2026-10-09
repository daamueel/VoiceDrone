import pytest

from flight.run_sitl import parse_args


def test_takeoff_circle_land_defaults_match_milestone_sequence() -> None:
    args = parse_args(["takeoff_circle_land"])

    assert args.circle_behavior == "circle"
    assert args.target_altitude == pytest.approx(5.0)
    assert args.radius == pytest.approx(10.0)
    assert args.speed == pytest.approx(1.0)
    assert args.angular_velocity is None
    assert args.duration is None


def test_takeoff_circle_land_accepts_explicit_circle_options() -> None:
    args = parse_args(
        [
            "takeoff_circle_land",
            "--circle-behavior",
            "circle_centripetal",
            "--target-altitude",
            "3.0",
            "--radius",
            "5.0",
            "--angular-velocity",
            "-0.2",
            "--duration",
            "20.0",
        ]
    )

    assert args.circle_behavior == "circle_centripetal"
    assert args.target_altitude == pytest.approx(3.0)
    assert args.radius == pytest.approx(5.0)
    assert args.angular_velocity == pytest.approx(-0.2)
    assert args.duration == pytest.approx(20.0)
