"""Run independently selectable VoiceDrone behaviors against PX4 SITL."""

import argparse
import asyncio
import time

from voicedrone.circle import Circle
from voicedrone.px4_offboard_adapter import PX4OffboardAdapter
from voicedrone.sitl_log import SitlLogger
from voicedrone.takeoff import Takeoff
from voicedrone.trajectory import TrajectoryPoint


async def land_and_log(
    adapter: PX4OffboardAdapter,
    log: SitlLogger,
    command: TrajectoryPoint,
) -> None:
    """Perform the runner's separate landing action and record it."""

    print("Runner action: landing")
    await adapter.land()
    landing_started = time.monotonic()
    while adapter.state().armed:
        log.write(
            time.monotonic() - landing_started,
            "landing",
            command,
            adapter.state(),
        )
        await asyncio.sleep(0.1)
    await adapter.wait_until_disarmed(timeout_s=30.0)
    log.write(
        time.monotonic() - landing_started,
        "landing",
        command,
        adapter.state(),
    )
    print("Landing complete: vehicle disarmed")


async def run_takeoff(args: argparse.Namespace) -> None:
    behavior = Takeoff(
        target_altitude=args.target_altitude,
        ascent_speed=args.ascent_speed,
        position_tolerance=args.position_tolerance,
    )
    adapter = PX4OffboardAdapter(args.connection)
    armed = False
    completed = False

    with SitlLogger("takeoff") as log:
        print(f"Log: {log.path}")
        try:
            await adapter.connect()
            await adapter.wait_until_ready()
            reference = adapter.state()
            command = behavior.point_at(0.0, reference)
            await adapter.send(command)
            await adapter.arm()
            armed = True
            await adapter.start_offboard()

            started = time.monotonic()
            timeout_s = behavior.duration + args.completion_timeout
            while True:
                trajectory_time = time.monotonic() - started
                command = behavior.point_at(trajectory_time, reference)
                await adapter.send(command)
                measured = adapter.state()
                log.write(trajectory_time, "takeoff", command, measured)
                if (
                    trajectory_time >= behavior.duration
                    and behavior.is_complete(reference, measured)
                ):
                    completed = True
                    print(
                        "Takeoff complete: "
                        f"target_down={behavior.target_down(reference):.3f} m, "
                        f"measured_down={measured.down_m:.3f} m"
                    )
                    break
                if trajectory_time > timeout_s:
                    raise TimeoutError("takeoff did not reach its altitude tolerance")
                await asyncio.sleep(0.05)
        finally:
            try:
                if armed:
                    await land_and_log(adapter, log, command)
            finally:
                await adapter.close()

    if not completed:
        raise RuntimeError("takeoff behavior did not complete")


async def run_circle(args: argparse.Namespace) -> None:
    behavior = Circle(
        radius=args.radius,
        speed=args.speed,
        angular_velocity=args.angular_velocity,
        duration=args.duration,
        phase=args.phase,
    )
    adapter = PX4OffboardAdapter(args.connection)
    armed = False
    completed = False

    with SitlLogger("circle") as log:
        print(f"Log: {log.path}")
        try:
            await adapter.connect()
            await adapter.wait_until_ready()
            ground_reference = adapter.state()
            command = TrajectoryPoint(
                north_m=ground_reference.north_m,
                east_m=ground_reference.east_m,
                down_m=ground_reference.down_m - args.setup_altitude,
                yaw_rad=ground_reference.yaw_rad,
            )

            await adapter.arm()
            armed = True
            print(
                "Runner setup: PX4 action takeoff to "
                f"{args.setup_altitude:.1f} m"
            )
            await adapter.action_takeoff(args.setup_altitude)

            setup_started = time.monotonic()
            settled_since: float | None = None
            while True:
                now = time.monotonic()
                measured = adapter.state()
                log.write(
                    now - setup_started,
                    "setup_takeoff",
                    command,
                    measured,
                )
                altitude_gain = ground_reference.down_m - measured.down_m
                settled = (
                    altitude_gain >= args.setup_altitude - 0.5
                    and abs(measured.down_m_s) <= 0.3
                )
                if settled:
                    settled_since = now if settled_since is None else settled_since
                    if now - settled_since >= 1.0:
                        break
                else:
                    settled_since = None
                if now - setup_started > args.setup_timeout:
                    raise TimeoutError("runner setup takeoff did not settle")
                await asyncio.sleep(0.1)

            reference = adapter.state()
            center_north, center_east = behavior.center(reference)
            command = behavior.point_at(0.0, reference)
            await adapter.send(command)
            await adapter.start_offboard()
            print(
                "Circle start: "
                f"radius={behavior.radius:.3f} m, "
                f"speed={behavior.speed:.3f} m/s, "
                f"angular_velocity={behavior.angular_velocity:.3f} rad/s, "
                f"duration={behavior.duration:.3f} s, "
                f"center=({center_north:.3f}, {center_east:.3f}) N/E"
            )

            started = time.monotonic()
            while True:
                trajectory_time = time.monotonic() - started
                command = behavior.point_at(trajectory_time, reference)
                await adapter.send(command)
                log.write(
                    trajectory_time,
                    "circle",
                    command,
                    adapter.state(),
                )
                if behavior.is_complete(trajectory_time):
                    completed = True
                    print("Circle complete")
                    break
                await asyncio.sleep(0.05)
        finally:
            try:
                if armed:
                    await land_and_log(adapter, log, command)
            finally:
                await adapter.close()

    if not completed:
        raise RuntimeError("circle behavior did not complete")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="behavior", required=True)
    takeoff = subparsers.add_parser("takeoff", help="run takeoff, then land")
    takeoff.add_argument("--target-altitude", type=float, default=5.0)
    takeoff.add_argument("--ascent-speed", type=float, default=1.0)
    takeoff.add_argument("--position-tolerance", type=float, default=0.25)
    takeoff.add_argument("--completion-timeout", type=float, default=15.0)
    takeoff.add_argument(
        "--connection", default="udpin://0.0.0.0:14540"
    )
    circle = subparsers.add_parser(
        "circle", help="set up airborne state, run circle, then land"
    )
    circle.add_argument("--radius", type=float, default=10.0)
    circle.add_argument("--speed", type=float, default=1.0)
    circle.add_argument("--angular-velocity", type=float)
    circle.add_argument("--duration", type=float)
    circle.add_argument("--phase", type=float, default=0.0)
    circle.add_argument("--setup-altitude", type=float, default=5.0)
    circle.add_argument("--setup-timeout", type=float, default=30.0)
    circle.add_argument(
        "--connection", default="udpin://0.0.0.0:14540"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.behavior == "takeoff":
        asyncio.run(run_takeoff(args))
    elif args.behavior == "circle":
        asyncio.run(run_circle(args))


if __name__ == "__main__":
    main()
