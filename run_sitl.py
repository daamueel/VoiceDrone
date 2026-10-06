"""Run independently selectable VoiceDrone behaviors against PX4 SITL."""

import argparse
import asyncio
import math
import time

from voicedrone.centered_circle import CenteredCircle
from voicedrone.px4_offboard_adapter import PX4OffboardAdapter
from voicedrone.side_circle import SideCircle
from voicedrone.sitl_log import SitlLogger
from voicedrone.takeoff import Takeoff
from voicedrone.trajectory import TrajectoryPoint, VehicleState


def angle_difference(first: float, second: float) -> float:
    return math.atan2(math.sin(first - second), math.cos(first - second))


async def land_and_log(
    adapter: PX4OffboardAdapter,
    log: SitlLogger,
    command: TrajectoryPoint,
) -> None:
    """Perform the runner's separate landing action and record it."""

    print("Runner action: landing")
    await adapter.stop_offboard()
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


async def wait_for_setup_takeoff(
    args: argparse.Namespace,
    adapter: PX4OffboardAdapter,
    log: SitlLogger,
    ground_reference: VehicleState,
    command: TrajectoryPoint,
) -> None:
    print(f"Runner setup: PX4 action takeoff to {args.setup_altitude:.1f} m")
    await adapter.action_takeoff(args.setup_altitude)
    setup_started = time.monotonic()
    settled_since: float | None = None
    while True:
        now = time.monotonic()
        measured = adapter.state()
        log.write(now - setup_started, "setup_takeoff", command, measured)
        altitude_gain = ground_reference.down_m - measured.down_m
        settled = (
            altitude_gain >= args.setup_altitude - 0.5
            and abs(measured.down_m_s) <= 0.3
        )
        if settled:
            settled_since = now if settled_since is None else settled_since
            if now - settled_since >= 1.0:
                return
        else:
            settled_since = None
        if now - setup_started > args.setup_timeout:
            raise TimeoutError("runner setup takeoff did not settle")
        await asyncio.sleep(0.1)


async def align_side_circle_yaw(
    adapter: PX4OffboardAdapter,
    log: SitlLogger,
    command: TrajectoryPoint,
    timeout_s: float = 15.0,
) -> None:
    """Align center-facing yaw before starting circular-motion time."""

    started = time.monotonic()
    settled_since: float | None = None
    while True:
        now = time.monotonic()
        await adapter.send(command)
        measured = adapter.state()
        log.write(now - started, "circle_alignment", command, measured)
        settled = (
            abs(angle_difference(measured.yaw_rad, command.yaw_rad)) <= 0.08
            and abs(measured.yaw_rate_rad_s) <= 0.15
        )
        if settled:
            settled_since = now if settled_since is None else settled_since
            if now - settled_since >= 1.0:
                return
        else:
            settled_since = None
        if now - started > timeout_s:
            raise TimeoutError("center-facing yaw alignment did not settle")
        await asyncio.sleep(0.05)


async def execute_circle(
    adapter: PX4OffboardAdapter,
    log: SitlLogger,
    behavior: SideCircle,
    reference: VehicleState,
    label: str,
) -> TrajectoryPoint:
    center_north, center_east = behavior.center(reference)
    print(
        f"{label} start: "
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
        log.write(trajectory_time, "circle", command, adapter.state())
        if behavior.is_complete(trajectory_time):
            print(f"{label} complete")
            return command
        await asyncio.sleep(0.05)


async def run_side_circle(args: argparse.Namespace) -> None:
    behavior = SideCircle(
        radius=args.radius,
        speed=args.speed,
        angular_velocity=args.angular_velocity,
        duration=args.duration,
        phase=args.phase,
    )
    adapter = PX4OffboardAdapter(args.connection)
    armed = False
    completed = False

    with SitlLogger("circle_side") as log:
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
            await wait_for_setup_takeoff(
                args, adapter, log, ground_reference, command
            )

            reference = adapter.state()
            command = behavior.point_at(0.0, reference)
            await adapter.send(command)
            await adapter.start_offboard()
            await align_side_circle_yaw(adapter, log, command)
            command = await execute_circle(
                adapter, log, behavior, reference, "Side circle"
            )
            completed = True
        finally:
            try:
                if armed:
                    await land_and_log(adapter, log, command)
            finally:
                await adapter.close()

    if not completed:
        raise RuntimeError("side circle behavior did not complete")


async def run_centered_circle(args: argparse.Namespace) -> None:
    behavior = CenteredCircle(
        radius=args.radius,
        speed=args.speed,
        angular_velocity=args.angular_velocity,
        duration=args.duration,
        entry_speed=args.entry_speed,
    )
    adapter = PX4OffboardAdapter(args.connection)
    armed = False
    completed = False

    with SitlLogger("circle_centered") as log:
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
            await wait_for_setup_takeoff(
                args, adapter, log, ground_reference, command
            )

            center_reference = adapter.state()
            command = behavior.entry_point_at(0.0, center_reference)
            await adapter.send(command)
            await adapter.start_offboard()
            print(
                "Centered circle entry: "
                f"distance={behavior.radius:.3f} m, "
                f"speed={behavior.entry_speed:.3f} m/s, "
                f"duration={behavior.entry_duration:.3f} s"
            )

            entry_started = time.monotonic()
            settled_since: float | None = None
            endpoint = behavior.entry_point_at(
                behavior.entry_duration, center_reference
            )
            while True:
                now = time.monotonic()
                entry_time = now - entry_started
                command = behavior.entry_point_at(entry_time, center_reference)
                await adapter.send(command)
                measured = adapter.state()
                log.write(entry_time, "circle_entry", command, measured)
                position_error = math.hypot(
                    measured.north_m - endpoint.north_m,
                    measured.east_m - endpoint.east_m,
                )
                horizontal_speed = math.hypot(
                    measured.north_m_s, measured.east_m_s
                )
                settled = (
                    behavior.is_entry_complete(entry_time)
                    and position_error <= 0.25
                    and horizontal_speed <= 0.3
                )
                if settled:
                    settled_since = now if settled_since is None else settled_since
                    if now - settled_since >= 1.0:
                        break
                else:
                    settled_since = None
                if entry_time > behavior.entry_duration + args.entry_timeout:
                    raise TimeoutError("centered circle entry did not settle")
                await asyncio.sleep(0.05)

            circumference_reference = behavior.circumference_reference(
                center_reference
            )
            circle = behavior.side_circle(center_reference)
            command = await execute_circle(
                adapter,
                log,
                circle,
                circumference_reference,
                "Centered circle",
            )
            completed = True
        finally:
            try:
                if armed:
                    await land_and_log(adapter, log, command)
            finally:
                await adapter.close()

    if not completed:
        raise RuntimeError("centered circle behavior did not complete")


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
    circle_side = subparsers.add_parser(
        "circle-side", help="start on a circle circumference, then land"
    )
    circle_side.add_argument("--radius", type=float, default=10.0)
    circle_side.add_argument("--speed", type=float, default=1.0)
    circle_side.add_argument("--angular-velocity", type=float)
    circle_side.add_argument("--duration", type=float)
    circle_side.add_argument("--phase", type=float, default=0.0)
    circle_side.add_argument("--setup-altitude", type=float, default=5.0)
    circle_side.add_argument("--setup-timeout", type=float, default=30.0)
    circle_side.add_argument(
        "--connection", default="udpin://0.0.0.0:14540"
    )
    circle_centered = subparsers.add_parser(
        "circle-centered", help="center circle on airborne start, then land"
    )
    circle_centered.add_argument("--radius", type=float, default=10.0)
    circle_centered.add_argument("--speed", type=float, default=1.0)
    circle_centered.add_argument("--angular-velocity", type=float)
    circle_centered.add_argument("--duration", type=float)
    circle_centered.add_argument("--entry-speed", type=float, default=1.0)
    circle_centered.add_argument("--entry-timeout", type=float, default=15.0)
    circle_centered.add_argument("--setup-altitude", type=float, default=5.0)
    circle_centered.add_argument("--setup-timeout", type=float, default=30.0)
    circle_centered.add_argument(
        "--connection", default="udpin://0.0.0.0:14540"
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    command_runners = {
        "takeoff": run_takeoff,
        "circle-side": run_side_circle,
        "circle-centered": run_centered_circle,
    }
    asyncio.run(command_runners[args.behavior](args))


if __name__ == "__main__":
    main()
