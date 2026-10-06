"""Analyze a VoiceDrone SITL CSV log and create its top-down N/E plot."""

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def angle_difference(first: float, second: float) -> float:
    return math.atan2(math.sin(first - second), math.cos(first - second))


def values(rows: list[dict[str, str]], name: str) -> np.ndarray:
    return np.array([float(row[name]) for row in rows])


def save_plot(
    path: Path,
    measured_north: np.ndarray,
    measured_east: np.ndarray,
    command_north: np.ndarray,
    command_east: np.ndarray,
    title: str,
    center: tuple[float, float] | None = None,
    entry: tuple[np.ndarray, np.ndarray] | None = None,
) -> Path:
    figure, axis = plt.subplots(figsize=(7, 7))
    axis.plot(measured_east, measured_north, label="measured", linewidth=2)
    axis.plot(command_east, command_north, "--", label="commanded")
    if entry is not None:
        axis.plot(entry[1], entry[0], ":", label="entry", linewidth=2)
    axis.scatter(measured_east[0], measured_north[0], marker="o", label="start")
    if center is not None:
        axis.scatter(center[1], center[0], marker="x", s=80, label="center")
    axis.set_xlabel("East (m)")
    axis.set_ylabel("North (m)")
    axis.set_title(title)
    axis.axis("equal")
    axis.grid(True)
    axis.legend()
    figure.tight_layout()

    output = path.with_name(f"{path.stem}_ne.png")
    figure.savefig(output, dpi=160)
    plt.close(figure)
    print(f"plot={output}")
    return output


def analyze_takeoff(path: Path, takeoff: list[dict[str, str]]) -> Path:
    north = values(takeoff, "measured_north_m")
    east = values(takeoff, "measured_east_m")
    down = values(takeoff, "measured_down_m")
    command_north = values(takeoff, "command_north_m")
    command_east = values(takeoff, "command_east_m")
    command_down = values(takeoff, "command_down_m")
    yaw = values(takeoff, "measured_yaw_rad")

    altitude_gain = down[0] - down[-1]
    target_gain = command_down[0] - command_down[-1]
    final_vertical_error = abs(down[-1] - command_down[-1])
    lateral_drift = max(
        math.hypot(n - north[0], e - east[0])
        for n, e in zip(north, east, strict=True)
    )
    yaw_change = abs(angle_difference(yaw[-1], yaw[0]))
    peak_vertical_speed = np.max(np.abs(values(takeoff, "measured_down_m_s")))

    print(f"samples={len(takeoff)}")
    print(f"target_altitude_gain_m={target_gain:.3f}")
    print(f"measured_altitude_gain_m={altitude_gain:.3f}")
    print(f"final_vertical_error_m={final_vertical_error:.3f}")
    print(f"maximum_lateral_drift_m={lateral_drift:.3f}")
    print(f"peak_vertical_speed_m_s={peak_vertical_speed:.3f}")
    print(f"absolute_yaw_change_rad={yaw_change:.3f}")

    return save_plot(
        path,
        north,
        east,
        command_north,
        command_east,
        "SITL takeoff: top-down local N/E",
    )


def fit_circle_center(north: np.ndarray, east: np.ndarray) -> tuple[float, float]:
    coefficients = np.column_stack((2.0 * north, 2.0 * east, np.ones(north.size)))
    solution, *_ = np.linalg.lstsq(
        coefficients, north * north + east * east, rcond=None
    )
    return float(solution[0]), float(solution[1])


def angular_rate(
    trajectory_time: np.ndarray,
    north: np.ndarray,
    east: np.ndarray,
    center_north: float,
    center_east: float,
) -> float:
    angles = np.unwrap(np.arctan2(east - center_east, north - center_north))
    return float(np.polyfit(trajectory_time, angles, 1)[0])


def analyze_circle(
    path: Path,
    circle: list[dict[str, str]],
    entry: list[dict[str, str]],
) -> Path:
    trajectory_time = values(circle, "trajectory_time_s")
    north = values(circle, "measured_north_m")
    east = values(circle, "measured_east_m")
    down = values(circle, "measured_down_m")
    north_m_s = values(circle, "measured_north_m_s")
    east_m_s = values(circle, "measured_east_m_s")
    yaw = values(circle, "measured_yaw_rad")
    yaw_rate = values(circle, "measured_yaw_rate_rad_s")
    command_north = values(circle, "command_north_m")
    command_east = values(circle, "command_east_m")
    command_down = values(circle, "command_down_m")
    command_north_m_s = values(circle, "command_north_m_s")
    command_east_m_s = values(circle, "command_east_m_s")
    command_yaw_rate = values(circle, "command_yaw_rate_rad_s")

    center_north, center_east = fit_circle_center(command_north, command_east)
    command_radius = np.hypot(
        command_north - center_north, command_east - center_east
    )
    measured_radius = np.hypot(north - center_north, east - center_east)
    command_speed = np.hypot(command_north_m_s, command_east_m_s)
    measured_speed = np.hypot(north_m_s, east_m_s)
    radial_error = measured_radius - np.mean(command_radius)
    altitude_error = down - command_down
    yaw_change = np.unwrap(yaw) - np.unwrap(yaw)[0]
    expected_yaw = np.arctan2(center_east - east, center_north - north)
    heading_error = np.arctan2(
        np.sin(yaw - expected_yaw), np.cos(yaw - expected_yaw)
    )

    print(f"samples={len(circle)}")
    print(f"circle_duration_s={trajectory_time[-1] - trajectory_time[0]:.3f}")
    print(f"commanded_radius_m={np.mean(command_radius):.3f}")
    print(f"measured_mean_radius_m={np.mean(measured_radius):.3f}")
    print(f"radial_rmse_m={np.sqrt(np.mean(radial_error**2)):.3f}")
    print(f"commanded_mean_speed_m_s={np.mean(command_speed):.3f}")
    print(f"measured_mean_speed_m_s={np.mean(measured_speed):.3f}")
    print(
        "commanded_angular_velocity_rad_s="
        f"{angular_rate(trajectory_time, command_north, command_east, center_north, center_east):.4f}"
    )
    print(
        "measured_angular_velocity_rad_s="
        f"{angular_rate(trajectory_time, north, east, center_north, center_east):.4f}"
    )
    print(f"mean_altitude_error_m={np.mean(np.abs(altitude_error)):.3f}")
    print(f"maximum_altitude_error_m={np.max(np.abs(altitude_error)):.3f}")
    print(f"altitude_range_m={np.ptp(down):.3f}")
    print(f"maximum_absolute_yaw_change_rad={np.max(np.abs(yaw_change)):.3f}")
    print(f"mean_center_heading_error_rad={np.mean(np.abs(heading_error)):.4f}")
    print(f"maximum_center_heading_error_rad={np.max(np.abs(heading_error)):.4f}")
    print(f"commanded_mean_yaw_rate_rad_s={np.mean(command_yaw_rate):.4f}")
    print(f"measured_mean_yaw_rate_rad_s={np.mean(yaw_rate):.4f}")

    entry_plot: tuple[np.ndarray, np.ndarray] | None = None
    if entry:
        entry_north = values(entry, "measured_north_m")
        entry_east = values(entry, "measured_east_m")
        entry_yaw = values(entry, "measured_yaw_rad")
        entry_radius = np.hypot(
            entry_north - center_north, entry_east - center_east
        )
        valid = entry_radius > 0.5
        if np.any(valid):
            entry_expected_yaw = np.arctan2(
                center_east - entry_east[valid],
                center_north - entry_north[valid],
            )
            entry_heading_error = np.arctan2(
                np.sin(entry_yaw[valid] - entry_expected_yaw),
                np.cos(entry_yaw[valid] - entry_expected_yaw),
            )
            print(
                "maximum_entry_center_heading_error_rad="
                f"{np.max(np.abs(entry_heading_error)):.4f}"
            )
        entry_plot = entry_north, entry_east

    return save_plot(
        path,
        north,
        east,
        command_north,
        command_east,
        "SITL circle: top-down local N/E",
        center=(center_north, center_east),
        entry=entry_plot,
    )


def analyze(path: Path) -> Path:
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    circle = [row for row in rows if row["phase"] == "circle"]
    if circle:
        entry = [row for row in rows if row["phase"] == "circle_entry"]
        return analyze_circle(path, circle, entry)
    takeoff = [row for row in rows if row["phase"] == "takeoff"]
    if takeoff:
        return analyze_takeoff(path, takeoff)
    raise ValueError("log contains no supported behavior samples")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    analyze(args.log)


if __name__ == "__main__":
    main()
