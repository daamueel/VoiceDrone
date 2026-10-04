"""Deterministic local-NED circular trajectory."""

import math

from .trajectory import TrajectoryPoint, VehicleState


class Circle:
    """Fly a level circle initialized from the measured airborne position."""

    def __init__(
        self,
        radius: float = 5.0,
        *,
        speed: float | None = None,
        angular_velocity: float | None = None,
        duration: float | None = None,
        phase: float = 0.0,
    ) -> None:
        if not math.isfinite(radius) or radius <= 0.0:
            raise ValueError("radius must be finite and greater than zero")
        if not math.isfinite(phase):
            raise ValueError("phase must be finite")
        if speed is not None and (not math.isfinite(speed) or speed <= 0.0):
            raise ValueError("speed must be finite and greater than zero")
        if angular_velocity is not None and (
            not math.isfinite(angular_velocity) or angular_velocity == 0.0
        ):
            raise ValueError("angular_velocity must be finite and nonzero")

        if angular_velocity is None:
            resolved_speed = 1.0 if speed is None else speed
            resolved_angular_velocity = resolved_speed / radius
        else:
            resolved_angular_velocity = angular_velocity
            derived_speed = abs(angular_velocity) * radius
            if speed is not None and not math.isclose(
                speed, derived_speed, rel_tol=1e-9, abs_tol=1e-9
            ):
                raise ValueError(
                    "speed conflicts with abs(angular_velocity) * radius"
                )
            resolved_speed = derived_speed

        if duration is None:
            resolved_duration = 2.0 * math.pi / abs(resolved_angular_velocity)
        elif not math.isfinite(duration) or duration <= 0.0:
            raise ValueError("duration must be finite and greater than zero")
        else:
            resolved_duration = duration

        self.radius = radius
        self.speed = resolved_speed
        self.angular_velocity = resolved_angular_velocity
        self.duration = resolved_duration
        self.phase = phase

    def center(self, reference: VehicleState) -> tuple[float, float]:
        """Return the N/E center that puts the reference on the circumference."""

        return (
            reference.north_m - self.radius * math.cos(self.phase),
            reference.east_m - self.radius * math.sin(self.phase),
        )

    def point_at(
        self, trajectory_time: float, reference: VehicleState
    ) -> TrajectoryPoint:
        """Return the circular setpoint at explicit trajectory time."""

        if not math.isfinite(trajectory_time):
            raise ValueError("trajectory_time must be finite")

        elapsed = min(max(0.0, trajectory_time), self.duration)
        theta = self.phase + self.angular_velocity * elapsed
        center_north, center_east = self.center(reference)
        moving = 0.0 <= trajectory_time < self.duration
        north_velocity = -self.radius * math.sin(theta) * self.angular_velocity
        east_velocity = self.radius * math.cos(theta) * self.angular_velocity

        return TrajectoryPoint(
            north_m=center_north + self.radius * math.cos(theta),
            east_m=center_east + self.radius * math.sin(theta),
            down_m=reference.down_m,
            north_m_s=north_velocity if moving else 0.0,
            east_m_s=east_velocity if moving else 0.0,
            yaw_rad=reference.yaw_rad,
        )

    def is_complete(self, trajectory_time: float) -> bool:
        """Return whether the requested circular-motion duration has elapsed."""

        if not math.isfinite(trajectory_time):
            raise ValueError("trajectory_time must be finite")
        return trajectory_time >= self.duration
