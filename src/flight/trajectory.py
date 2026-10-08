"""PX4-independent trajectory data types using local NED coordinates."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TrajectoryPoint:
    """A commanded local-NED state at one explicit trajectory time."""

    north_m: float
    east_m: float
    down_m: float
    north_m_s: float = 0.0
    east_m_s: float = 0.0
    down_m_s: float = 0.0
    yaw_rad: float = 0.0
    yaw_rate_rad_s: float = 0.0


@dataclass(frozen=True)
class VehicleState:
    """Measured state needed by trajectory behaviors and SITL logging."""

    north_m: float
    east_m: float
    down_m: float
    north_m_s: float = 0.0
    east_m_s: float = 0.0
    down_m_s: float = 0.0
    yaw_rad: float = 0.0
    yaw_rate_rad_s: float = 0.0
    flight_mode: str = "UNKNOWN"
    armed: bool = False
