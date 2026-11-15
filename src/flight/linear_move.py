"""Straight local-NED move from fresh telemetry, holding the starting yaw."""

import math

from .trajectory import TrajectoryPoint, VehicleState


class LinearMove:
    def __init__(
        self, north_m: float, east_m: float, down_m: float,
        *, speed_m_s: float = 1.0,
        position_tolerance_m: float = 0.15,
        speed_tolerance_m_s: float = 0.2,
    ) -> None:
        values = (north_m, east_m, down_m, speed_m_s,
                  position_tolerance_m, speed_tolerance_m_s)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("move parameters must be finite")
        self.distance_m = math.sqrt(north_m**2 + east_m**2 + down_m**2)
        if self.distance_m <= 0 or speed_m_s <= 0:
            raise ValueError("move distance and speed must be positive")
        if position_tolerance_m <= 0 or speed_tolerance_m_s <= 0:
            raise ValueError("move tolerances must be positive")
        self.delta = (north_m, east_m, down_m)
        self.speed_m_s = speed_m_s
        self.position_tolerance_m = position_tolerance_m
        self.speed_tolerance_m_s = speed_tolerance_m_s

    @property
    def duration(self) -> float:
        return self.distance_m / self.speed_m_s

    def point_at(self, elapsed_s: float, reference: VehicleState) -> TrajectoryPoint:
        if not math.isfinite(elapsed_s):
            raise ValueError("elapsed time must be finite")
        fraction = min(max(elapsed_s / self.duration, 0.0), 1.0)
        moving = 0 <= elapsed_s < self.duration
        velocity = self.speed_m_s / self.distance_m if moving else 0.0
        north, east, down = self.delta
        return TrajectoryPoint(
            north_m=reference.north_m + north * fraction,
            east_m=reference.east_m + east * fraction,
            down_m=reference.down_m + down * fraction,
            north_m_s=north * velocity,
            east_m_s=east * velocity,
            down_m_s=down * velocity,
            yaw_rad=reference.yaw_rad,
        )

    def is_settled(self, reference: VehicleState, measured: VehicleState) -> bool:
        target = self.point_at(self.duration, reference)
        position_error = math.dist(
            (target.north_m, target.east_m, target.down_m),
            (measured.north_m, measured.east_m, measured.down_m),
        )
        velocity = math.sqrt(
            measured.north_m_s**2 + measured.east_m_s**2 + measured.down_m_s**2
        )
        return (
            math.isfinite(position_error) and math.isfinite(velocity)
            and position_error <= self.position_tolerance_m
            and velocity <= self.speed_tolerance_m_s
        )
