"""Center-facing circle around the vehicle's position before radial entry."""

import math

from .circle_side import CircleSide
from .trajectory import TrajectoryPoint, VehicleState


class CircleCentripetal:
    """Enter a circumference behind the vehicle, then face its start point."""

    def __init__(
        self,
        radius: float = 5.0,
        *,
        speed: float | None = None,
        angular_velocity: float | None = None,
        duration: float | None = None,
        entry_speed: float = 1.0,
    ) -> None:
        if not math.isfinite(entry_speed) or entry_speed <= 0.0:
            raise ValueError("entry_speed must be finite and greater than zero")
        template = CircleSide(
            radius,
            speed=speed,
            angular_velocity=angular_velocity,
            duration=duration,
        )
        self.radius = template.radius
        self.speed = template.speed
        self.angular_velocity = template.angular_velocity
        self.duration = template.duration
        self.entry_speed = entry_speed

    @property
    def entry_duration(self) -> float:
        return self.radius / self.entry_speed

    @property
    def return_duration(self) -> float:
        """Time needed to retrace the radial entry to the circle center."""

        return self.entry_duration

    def phase(self, reference: VehicleState) -> float:
        """Put the circumference entry behind the initial vehicle heading."""

        return math.atan2(
            math.sin(reference.yaw_rad - math.pi),
            math.cos(reference.yaw_rad - math.pi),
        )

    def center(self, reference: VehicleState) -> tuple[float, float]:
        return reference.north_m, reference.east_m

    def entry_point_at(
        self, entry_time: float, reference: VehicleState
    ) -> TrajectoryPoint:
        """Move radially backward while keeping the nose on the center."""

        if not math.isfinite(entry_time):
            raise ValueError("entry_time must be finite")
        elapsed = min(max(0.0, entry_time), self.entry_duration)
        distance = self.entry_speed * elapsed
        phase = self.phase(reference)
        moving = 0.0 <= entry_time < self.entry_duration
        return TrajectoryPoint(
            north_m=reference.north_m + distance * math.cos(phase),
            east_m=reference.east_m + distance * math.sin(phase),
            down_m=reference.down_m,
            north_m_s=self.entry_speed * math.cos(phase) if moving else 0.0,
            east_m_s=self.entry_speed * math.sin(phase) if moving else 0.0,
            yaw_rad=reference.yaw_rad,
        )

    def circumference_reference(self, reference: VehicleState) -> VehicleState:
        endpoint = self.entry_point_at(self.entry_duration, reference)
        return VehicleState(
            north_m=endpoint.north_m,
            east_m=endpoint.east_m,
            down_m=endpoint.down_m,
            yaw_rad=endpoint.yaw_rad,
        )

    def return_point_at(
        self, return_time: float, reference: VehicleState
    ) -> TrajectoryPoint:
        """Move from the circumference back to the original airborne start."""

        if not math.isfinite(return_time):
            raise ValueError("return_time must be finite")
        elapsed = min(max(0.0, return_time), self.return_duration)
        distance = self.radius - self.entry_speed * elapsed
        phase = self.phase(reference)
        moving = 0.0 <= return_time < self.return_duration
        return TrajectoryPoint(
            north_m=reference.north_m + distance * math.cos(phase),
            east_m=reference.east_m + distance * math.sin(phase),
            down_m=reference.down_m,
            north_m_s=-self.entry_speed * math.cos(phase) if moving else 0.0,
            east_m_s=-self.entry_speed * math.sin(phase) if moving else 0.0,
            yaw_rad=reference.yaw_rad,
        )

    def circle_segment(self, reference: VehicleState) -> CircleSide:
        """Return the circular segment whose center is the original position."""

        return CircleSide(
            self.radius,
            speed=self.speed,
            angular_velocity=self.angular_velocity,
            duration=self.duration,
            phase=self.phase(reference),
        )

    def is_entry_complete(self, entry_time: float) -> bool:
        if not math.isfinite(entry_time):
            raise ValueError("entry_time must be finite")
        return entry_time >= self.entry_duration

    def is_return_complete(self, return_time: float) -> bool:
        if not math.isfinite(return_time):
            raise ValueError("return_time must be finite")
        return return_time >= self.return_duration
