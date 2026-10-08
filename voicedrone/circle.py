"""Centered circular trajectory that holds its starting yaw."""

from dataclasses import replace

from .circle_centripetal import CircleCentripetal
from .side_circle import SideCircle
from .trajectory import TrajectoryPoint, VehicleState


class _FixedYawCircle(SideCircle):
    def point_at(
        self, trajectory_time: float, reference: VehicleState
    ) -> TrajectoryPoint:
        point = super().point_at(trajectory_time, reference)
        return replace(point, yaw_rad=reference.yaw_rad, yaw_rate_rad_s=0.0)


class Circle(CircleCentripetal):
    """Circle around the measured airborne start while holding its yaw."""

    def side_circle(self, reference: VehicleState) -> SideCircle:
        return _FixedYawCircle(
            self.radius,
            speed=self.speed,
            angular_velocity=self.angular_velocity,
            duration=self.duration,
            phase=self.phase(reference),
        )
