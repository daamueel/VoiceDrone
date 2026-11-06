"""Structured user-facing commands shared by keyboard and speech input."""

from dataclasses import dataclass
from enum import Enum
import math
from typing import TypeAlias


DEFAULT_TAKEOFF_ALTITUDE_M = 0.5
MIN_TAKEOFF_ALTITUDE_M = 0.1
MAX_TAKEOFF_ALTITUDE_M = 120.0

DEFAULT_CIRCLE_RADIUS_M = 0.5
MIN_CIRCLE_RADIUS_M = 0.1
MAX_CIRCLE_RADIUS_M = 1000.0
DEFAULT_CIRCLE_SPEED_M_S = 1.0


class CircleBehavior(str, Enum):
    """Existing low-level circle behavior selected by a user command."""

    CENTRIPETAL = "circle_centripetal"
    FIXED_YAW = "circle"
    SIDE = "circle_side"


class Direction(str, Enum):
    """Circle direction in PX4's local NED convention."""

    CLOCKWISE = "clockwise"
    COUNTERCLOCKWISE = "counterclockwise"

    @property
    def sign(self) -> float:
        return 1.0 if self is Direction.CLOCKWISE else -1.0


def _require_finite_range(
    value: float,
    *,
    name: str,
    minimum: float,
    maximum: float,
) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    if not minimum <= value <= maximum:
        raise ValueError(
            f"{name} must be between {minimum:g} and {maximum:g}"
        )


@dataclass(frozen=True, slots=True)
class TakeoffCommand:
    altitude_m: float = DEFAULT_TAKEOFF_ALTITUDE_M

    def __post_init__(self) -> None:
        _require_finite_range(
            self.altitude_m,
            name="takeoff altitude",
            minimum=MIN_TAKEOFF_ALTITUDE_M,
            maximum=MAX_TAKEOFF_ALTITUDE_M,
        )


@dataclass(frozen=True, slots=True)
class CircleCommand:
    behavior: CircleBehavior = CircleBehavior.CENTRIPETAL
    radius_m: float = DEFAULT_CIRCLE_RADIUS_M
    direction: Direction = Direction.CLOCKWISE

    def __post_init__(self) -> None:
        _require_finite_range(
            self.radius_m,
            name="circle radius",
            minimum=MIN_CIRCLE_RADIUS_M,
            maximum=MAX_CIRCLE_RADIUS_M,
        )

    @property
    def speed_m_s(self) -> float:
        return DEFAULT_CIRCLE_SPEED_M_S

    @property
    def angular_velocity_rad_s(self) -> float:
        return self.direction.sign * self.speed_m_s / self.radius_m

    @property
    def duration_s(self) -> float:
        return 2.0 * math.pi / abs(self.angular_velocity_rad_s)


@dataclass(frozen=True, slots=True)
class LandCommand:
    pass


@dataclass(frozen=True, slots=True)
class StatusCommand:
    pass


@dataclass(frozen=True, slots=True)
class HelpCommand:
    pass


@dataclass(frozen=True, slots=True)
class ExitCommand:
    pass


Command: TypeAlias = (
    TakeoffCommand
    | CircleCommand
    | LandCommand
    | StatusCommand
    | HelpCommand
    | ExitCommand
)
