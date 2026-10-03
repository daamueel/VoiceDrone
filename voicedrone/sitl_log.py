"""CSV logging for reproducible SITL behavior verification."""

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import TextIO

from .trajectory import TrajectoryPoint, VehicleState


FIELDS = (
    "timestamp_utc",
    "trajectory_time_s",
    "phase",
    "command_north_m",
    "command_east_m",
    "command_down_m",
    "command_north_m_s",
    "command_east_m_s",
    "command_down_m_s",
    "command_yaw_rad",
    "command_yaw_rate_rad_s",
    "measured_north_m",
    "measured_east_m",
    "measured_down_m",
    "measured_north_m_s",
    "measured_east_m_s",
    "measured_down_m_s",
    "measured_yaw_rad",
    "measured_yaw_rate_rad_s",
    "flight_mode",
    "armed",
)


class SitlLogger:
    def __init__(self, test_name: str, directory: Path = Path("logs")) -> None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / f"sitl_{timestamp}_{test_name}.csv"
        self._file: TextIO = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.DictWriter(self._file, fieldnames=FIELDS)
        self._writer.writeheader()

    def write(
        self,
        trajectory_time_s: float,
        phase: str,
        command: TrajectoryPoint,
        measured: VehicleState,
    ) -> None:
        self._writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "trajectory_time_s": f"{trajectory_time_s:.6f}",
                "phase": phase,
                "command_north_m": command.north_m,
                "command_east_m": command.east_m,
                "command_down_m": command.down_m,
                "command_north_m_s": command.north_m_s,
                "command_east_m_s": command.east_m_s,
                "command_down_m_s": command.down_m_s,
                "command_yaw_rad": command.yaw_rad,
                "command_yaw_rate_rad_s": command.yaw_rate_rad_s,
                "measured_north_m": measured.north_m,
                "measured_east_m": measured.east_m,
                "measured_down_m": measured.down_m,
                "measured_north_m_s": measured.north_m_s,
                "measured_east_m_s": measured.east_m_s,
                "measured_down_m_s": measured.down_m_s,
                "measured_yaw_rad": measured.yaw_rad,
                "measured_yaw_rate_rad_s": measured.yaw_rate_rad_s,
                "flight_mode": measured.flight_mode,
                "armed": measured.armed,
            }
        )
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "SitlLogger":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
