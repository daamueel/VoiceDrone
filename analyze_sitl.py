"""Analyze a VoiceDrone SITL CSV log and create its top-down N/E plot."""

import argparse
import csv
import math
from pathlib import Path

import matplotlib.pyplot as plt


def angle_difference(first: float, second: float) -> float:
    return math.atan2(math.sin(first - second), math.cos(first - second))


def analyze(path: Path) -> Path:
    with path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    takeoff = [row for row in rows if row["phase"] == "takeoff"]
    if not takeoff:
        raise ValueError("log contains no takeoff samples")

    def values(name: str) -> list[float]:
        return [float(row[name]) for row in takeoff]

    north = values("measured_north_m")
    east = values("measured_east_m")
    down = values("measured_down_m")
    command_north = values("command_north_m")
    command_east = values("command_east_m")
    command_down = values("command_down_m")
    yaw = values("measured_yaw_rad")

    altitude_gain = down[0] - down[-1]
    target_gain = command_down[0] - command_down[-1]
    final_vertical_error = abs(down[-1] - command_down[-1])
    lateral_drift = max(
        math.hypot(n - north[0], e - east[0])
        for n, e in zip(north, east, strict=True)
    )
    yaw_change = abs(angle_difference(yaw[-1], yaw[0]))
    peak_vertical_speed = max(abs(value) for value in values("measured_down_m_s"))

    print(f"samples={len(takeoff)}")
    print(f"target_altitude_gain_m={target_gain:.3f}")
    print(f"measured_altitude_gain_m={altitude_gain:.3f}")
    print(f"final_vertical_error_m={final_vertical_error:.3f}")
    print(f"maximum_lateral_drift_m={lateral_drift:.3f}")
    print(f"peak_vertical_speed_m_s={peak_vertical_speed:.3f}")
    print(f"absolute_yaw_change_rad={yaw_change:.3f}")

    figure, axis = plt.subplots(figsize=(7, 7))
    axis.plot(east, north, label="measured", linewidth=2)
    axis.plot(command_east, command_north, "--", label="commanded")
    axis.scatter(east[0], north[0], marker="o", label="start")
    axis.set_xlabel("East (m)")
    axis.set_ylabel("North (m)")
    axis.set_title("SITL takeoff: top-down local N/E")
    axis.axis("equal")
    axis.grid(True)
    axis.legend()
    figure.tight_layout()

    output = path.with_name(f"{path.stem}_ne.png")
    figure.savefig(output, dpi=160)
    plt.close(figure)
    print(f"plot={output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    analyze(args.log)


if __name__ == "__main__":
    main()
