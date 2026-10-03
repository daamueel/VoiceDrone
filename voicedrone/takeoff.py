"""Deterministic local-NED takeoff trajectory."""

import math

from .trajectory import TrajectoryPoint, VehicleState


class Takeoff:
    """Climb vertically from a measured reference while holding N, E, and yaw."""

    def __init__(
        self,
        target_altitude: float = 5.0,
        ascent_speed: float = 1.0,
        position_tolerance: float = 0.25,
    ) -> None:
        values = (target_altitude, ascent_speed, position_tolerance)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("takeoff parameters must be finite")
        if target_altitude <= 0.0:
            raise ValueError("target_altitude must be greater than zero")
        if ascent_speed <= 0.0:
            raise ValueError("ascent_speed must be greater than zero")
        if position_tolerance <= 0.0:
            raise ValueError("position_tolerance must be greater than zero")

        self.target_altitude = target_altitude
        self.ascent_speed = ascent_speed
        self.position_tolerance = position_tolerance

    @property
    def duration(self) -> float:
        """Nominal climb time in seconds before holding the target altitude."""

        return self.target_altitude / self.ascent_speed

    def target_down(self, reference: VehicleState) -> float:
        """Return the NED down target relative to the measured starting down."""

        return reference.down_m - self.target_altitude

    def point_at(
        self, trajectory_time: float, reference: VehicleState
    ) -> TrajectoryPoint:
        """Return the setpoint at ``trajectory_time`` without using a clock."""

        if not math.isfinite(trajectory_time):
            raise ValueError("trajectory_time must be finite")

        elapsed = max(0.0, trajectory_time)
        climb_distance = min(self.target_altitude, self.ascent_speed * elapsed)
        climbing = elapsed < self.duration
        return TrajectoryPoint(
            north_m=reference.north_m,
            east_m=reference.east_m,
            down_m=reference.down_m - climb_distance,
            down_m_s=-self.ascent_speed if climbing else 0.0,
            yaw_rad=reference.yaw_rad,
        )

    def is_complete(self, reference: VehicleState, measured: VehicleState) -> bool:
        """Return whether measured altitude is within tolerance of the target."""

        return (
            abs(measured.down_m - self.target_down(reference))
            <= self.position_tolerance
        )
