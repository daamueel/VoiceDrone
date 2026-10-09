"""Run independently selectable VoiceDrone behaviors against PX4 SITL."""

import argparse
import asyncio
import math
import time

from .circle import Circle
from .circle_centripetal import CircleCentripetal
from .circle_side import CircleSide
from .px4_offboard_adapter import PX4OffboardAdapter
from .sitl_log import SitlLogger
from .takeoff import Takeoff
from .trajectory import TrajectoryPoint, VehicleState


def angle_difference(first: float, second: float) -> float:
    return math.atan2(math.sin(first - second), math.cos(first - second))


def positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("value must be finite and greater than zero")
    return parsed


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


async def execute_takeoff(
    adapter: PX4OffboardAdapter,
    log: SitlLogger,
    behavior: Takeoff,
    reference: VehicleState,
    settling_time: float,
    completion_timeout: float,
) -> TrajectoryPoint:
    """Execute and settle a takeoff without selecting the next action."""

    started = time.monotonic()
    timeout_s = behavior.duration + completion_timeout
    settled_since: float | None = None
    while True:
        trajectory_time = time.monotonic() - started
        command = behavior.point_at(trajectory_time, reference)
        await adapter.send(command)
        measured = adapter.state()
        log.write(trajectory_time, "takeoff", command, measured)
        settled = (
            trajectory_time >= behavior.duration
            and behavior.is_settled(reference, measured)
        )
        if settled:
            settled_since = (
                time.monotonic() if settled_since is None else settled_since
            )
            if time.monotonic() - settled_since >= settling_time:
                print(
                    "Takeoff settled: "
                    f"target_down={behavior.target_down(reference):.3f} m, "
                    f"measured_down={measured.down_m:.3f} m, "
                    f"vertical_speed={measured.down_m_s:.3f} m/s"
                )
                return command
        else:
            settled_since = None
        if trajectory_time > timeout_s:
            raise TimeoutError("takeoff did not reach its settling criteria")
        await asyncio.sleep(0.05)


async def run_takeoff(args: argparse.Namespace) -> None:
    behavior = Takeoff(
        target_altitude=args.target_altitude,
        ascent_speed=args.ascent_speed,
        position_tolerance=args.position_tolerance,
        vertical_speed_tolerance=args.vertical_speed_tolerance,
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
            command = await execute_takeoff(
                adapter,
                log,
                behavior,
                reference,
                args.settling_time,
                args.completion_timeout,
            )
            completed = True
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
        target_down = ground_reference.down_m - args.setup_altitude
        position_is_valid = all(
            math.isfinite(value)
            for value in (measured.north_m, measured.east_m, measured.down_m)
        )
        settled = (
            position_is_valid
            and abs(measured.down_m - target_down) <= args.setup_position_tolerance
            and abs(measured.down_m_s) <= args.setup_vertical_speed_tolerance
        )
        if settled:
            settled_since = now if settled_since is None else settled_since
            if now - settled_since >= args.setup_settling_time:
                return
        else:
            settled_since = None
        if now - setup_started > args.setup_timeout:
            raise TimeoutError("runner setup takeoff did not settle")
        await asyncio.sleep(0.1)


async def align_circle_side_yaw(
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
    behavior: CircleSide,
    reference: VehicleState,
    label: str,
    closure_timeout: float,
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
            break
        await asyncio.sleep(0.05)

    # The requested revolution is complete. Hold its endpoint until the
    # measured vehicle catches up; this time is separate from circle duration.
    command = behavior.point_at(behavior.duration, reference)
    closure_started = time.monotonic()
    settled_since: float | None = None
    while True:
        now = time.monotonic()
        await adapter.send(command)
        measured = adapter.state()
        log.write(now - closure_started, "circle_closure", command, measured)
        position_error = math.hypot(
            measured.north_m - command.north_m,
            measured.east_m - command.east_m,
        )
        horizontal_speed = math.hypot(
            measured.north_m_s, measured.east_m_s
        )
        settled = position_error <= 0.15 and horizontal_speed <= 0.2
        if settled:
            settled_since = now if settled_since is None else settled_since
            if now - settled_since >= 0.5:
                print(
                    f"{label} complete: endpoint error={position_error:.3f} m, "
                    f"closure time={now - closure_started:.3f} s"
                )
                return command
        else:
            settled_since = None
        if now - closure_started > closure_timeout:
            raise TimeoutError(f"{label} did not settle at its starting position")
        await asyncio.sleep(0.05)


async def return_centered_circle_to_start(
    adapter: PX4OffboardAdapter,
    log: SitlLogger,
    behavior: CircleCentripetal,
    center_reference: VehicleState,
    timeout_s: float,
) -> TrajectoryPoint:
    """Retrace radial entry and settle over the airborne starting point."""

    print(
        "Runner return to centered-circle start: "
        f"distance={behavior.radius:.3f} m, "
        f"speed={behavior.entry_speed:.3f} m/s"
    )
    started = time.monotonic()
    settled_since: float | None = None
    while True:
        now = time.monotonic()
        return_time = now - started
        command = behavior.return_point_at(return_time, center_reference)
        await adapter.send(command)
        measured = adapter.state()
        log.write(return_time, "circle_return", command, measured)
        position_error = math.hypot(
            measured.north_m - center_reference.north_m,
            measured.east_m - center_reference.east_m,
        )
        horizontal_speed = math.hypot(
            measured.north_m_s, measured.east_m_s
        )
        settled = (
            behavior.is_return_complete(return_time)
            and position_error <= 0.15
            and horizontal_speed <= 0.2
        )
        if settled:
            settled_since = now if settled_since is None else settled_since
            if now - settled_since >= 0.5:
                print(
                    "Centered-circle return complete: "
                    f"position error={position_error:.3f} m"
                )
                return command
        else:
            settled_since = None
        if return_time > behavior.return_duration + timeout_s:
            raise TimeoutError("centered circle did not settle at its starting point")
        await asyncio.sleep(0.05)


async def run_circle_side(args: argparse.Namespace) -> None:
    behavior = CircleSide(
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
            await align_circle_side_yaw(adapter, log, command)
            command = await execute_circle(
                adapter, log, behavior, reference, "Side circle", args.closure_timeout
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


async def execute_centered_circle_behavior(
    adapter: PX4OffboardAdapter,
    log: SitlLogger,
    behavior: CircleCentripetal,
    center_reference: VehicleState,
    label: str,
    entry_timeout: float,
    closure_timeout: float,
    return_timeout: float,
) -> TrajectoryPoint:
    """Execute entry, centered circle, and return with offboard already active."""

    print(
        f"{label} entry: "
        f"distance={behavior.radius:.3f} m, "
        f"speed={behavior.entry_speed:.3f} m/s, "
        f"duration={behavior.entry_duration:.3f} s"
    )

    entry_started = time.monotonic()
    settled_since: float | None = None
    endpoint = behavior.entry_point_at(behavior.entry_duration, center_reference)
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
        if entry_time > behavior.entry_duration + entry_timeout:
            raise TimeoutError("centered circle entry did not settle")
        await asyncio.sleep(0.05)

    circumference_reference = behavior.circumference_reference(center_reference)
    circle = behavior.circle_segment(center_reference)
    await execute_circle(
        adapter,
        log,
        circle,
        circumference_reference,
        label,
        closure_timeout,
    )
    return await return_centered_circle_to_start(
        adapter,
        log,
        behavior,
        center_reference,
        return_timeout,
    )


async def run_centered_circle(args: argparse.Namespace) -> None:
    behavior_class = (
        CircleCentripetal if args.behavior == "circle_centripetal" else Circle
    )
    behavior = behavior_class(
        radius=args.radius,
        speed=args.speed,
        angular_velocity=args.angular_velocity,
        duration=args.duration,
        entry_speed=args.entry_speed,
    )
    adapter = PX4OffboardAdapter(args.connection)
    armed = False
    completed = False

    with SitlLogger(args.behavior) as log:
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
            command = await execute_centered_circle_behavior(
                adapter,
                log,
                behavior,
                center_reference,
                args.behavior,
                args.entry_timeout,
                args.closure_timeout,
                args.return_timeout,
            )
            completed = True
        finally:
            try:
                if armed:
                    await land_and_log(adapter, log, command)
            finally:
                await adapter.close()

    if not completed:
        raise RuntimeError(f"{args.behavior} behavior did not complete")


async def run_takeoff_circle_land(args: argparse.Namespace) -> None:
    """Run deterministic takeoff, centered circle, return, then runner landing."""

    takeoff = Takeoff(
        target_altitude=args.target_altitude,
        ascent_speed=args.ascent_speed,
        position_tolerance=args.position_tolerance,
        vertical_speed_tolerance=args.vertical_speed_tolerance,
    )
    circle_class = (
        CircleCentripetal
        if args.circle_behavior == "circle_centripetal"
        else Circle
    )
    circle_behavior = circle_class(
        radius=args.radius,
        speed=args.speed,
        angular_velocity=args.angular_velocity,
        duration=args.duration,
        entry_speed=args.entry_speed,
    )
    adapter = PX4OffboardAdapter(args.connection)
    armed = False
    completed = False

    with SitlLogger("takeoff_circle_land") as log:
        print(f"Log: {log.path}")
        try:
            await adapter.connect()
            await adapter.wait_until_ready()
            ground_reference = adapter.state()
            command = takeoff.point_at(0.0, ground_reference)
            await adapter.send(command)
            await adapter.arm()
            armed = True
            await adapter.start_offboard()

            command = await execute_takeoff(
                adapter,
                log,
                takeoff,
                ground_reference,
                args.settling_time,
                args.completion_timeout,
            )

            center_reference = adapter.state()
            command = circle_behavior.entry_point_at(0.0, center_reference)
            await adapter.send(command)
            command = await execute_centered_circle_behavior(
                adapter,
                log,
                circle_behavior,
                center_reference,
                args.circle_behavior,
                args.entry_timeout,
                args.closure_timeout,
                args.return_timeout,
            )
            completed = True
        finally:
            try:
                if armed:
                    await land_and_log(adapter, log, command)
            finally:
                await adapter.close()

    if not completed:
        raise RuntimeError("takeoff-circle-land sequence did not complete")


def parse_args(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="behavior", required=True)
    takeoff = subparsers.add_parser("takeoff", help="run takeoff, then land")
    takeoff.add_argument("--target-altitude", type=float, default=5.0)
    takeoff.add_argument("--ascent-speed", type=float, default=1.0)
    takeoff.add_argument("--position-tolerance", type=float, default=0.25)
    takeoff.add_argument(
        "--vertical-speed-tolerance", type=positive_float, default=0.2
    )
    takeoff.add_argument("--settling-time", type=positive_float, default=1.0)
    takeoff.add_argument("--completion-timeout", type=float, default=15.0)
    takeoff.add_argument(
        "--connection", default="udpin://0.0.0.0:14540"
    )
    circle_side = subparsers.add_parser(
        "circle_side", help="start on a circle circumference, then land"
    )
    circle_side.add_argument("--radius", type=float, default=10.0)
    circle_side.add_argument("--speed", type=float, default=1.0)
    circle_side.add_argument("--angular-velocity", type=float)
    circle_side.add_argument("--duration", type=float)
    circle_side.add_argument("--phase", type=float, default=0.0)
    circle_side.add_argument("--setup-altitude", type=float, default=5.0)
    circle_side.add_argument("--setup-timeout", type=float, default=30.0)
    circle_side.add_argument(
        "--setup-position-tolerance", type=positive_float, default=0.25
    )
    circle_side.add_argument(
        "--setup-vertical-speed-tolerance", type=positive_float, default=0.2
    )
    circle_side.add_argument(
        "--setup-settling-time", type=positive_float, default=1.0
    )
    circle_side.add_argument("--closure-timeout", type=float, default=15.0)
    circle_side.add_argument(
        "--connection", default="udpin://0.0.0.0:14540"
    )
    for name, description in (
        ("circle_centripetal", "circle around airborne start while facing center"),
        ("circle", "circle around airborne start while holding starting yaw"),
    ):
        circle_parser = subparsers.add_parser(name, help=description)
        circle_parser.add_argument("--radius", type=float, default=10.0)
        circle_parser.add_argument("--speed", type=float, default=1.0)
        circle_parser.add_argument("--angular-velocity", type=float)
        circle_parser.add_argument("--duration", type=float)
        circle_parser.add_argument("--entry-speed", type=float, default=1.0)
        circle_parser.add_argument("--entry-timeout", type=float, default=15.0)
        circle_parser.add_argument(
            "--return-timeout", type=positive_float, default=15.0
        )
        circle_parser.add_argument("--setup-altitude", type=float, default=5.0)
        circle_parser.add_argument("--setup-timeout", type=float, default=30.0)
        circle_parser.add_argument(
            "--setup-position-tolerance", type=positive_float, default=0.25
        )
        circle_parser.add_argument(
            "--setup-vertical-speed-tolerance", type=positive_float, default=0.2
        )
        circle_parser.add_argument(
            "--setup-settling-time", type=positive_float, default=1.0
        )
        circle_parser.add_argument("--closure-timeout", type=float, default=15.0)
        circle_parser.add_argument(
            "--connection", default="udpin://0.0.0.0:14540"
        )
    sequence = subparsers.add_parser(
        "takeoff_circle_land",
        help="run deterministic takeoff, centered circle, return, and landing",
    )
    sequence.add_argument(
        "--circle-behavior",
        choices=("circle", "circle_centripetal"),
        default="circle",
    )
    sequence.add_argument("--target-altitude", type=float, default=5.0)
    sequence.add_argument("--ascent-speed", type=float, default=1.0)
    sequence.add_argument("--position-tolerance", type=float, default=0.25)
    sequence.add_argument(
        "--vertical-speed-tolerance", type=positive_float, default=0.2
    )
    sequence.add_argument("--settling-time", type=positive_float, default=1.0)
    sequence.add_argument("--completion-timeout", type=float, default=15.0)
    sequence.add_argument("--radius", type=float, default=10.0)
    sequence.add_argument("--speed", type=float, default=1.0)
    sequence.add_argument("--angular-velocity", type=float)
    sequence.add_argument("--duration", type=float)
    sequence.add_argument("--entry-speed", type=float, default=1.0)
    sequence.add_argument("--entry-timeout", type=float, default=15.0)
    sequence.add_argument(
        "--return-timeout", type=positive_float, default=15.0
    )
    sequence.add_argument("--closure-timeout", type=float, default=15.0)
    sequence.add_argument(
        "--connection", default="udpin://0.0.0.0:14540"
    )
    return parser.parse_args(arguments)


def main() -> None:
    args = parse_args()
    command_runners = {
        "takeoff": run_takeoff,
        "circle_side": run_circle_side,
        "circle_centripetal": run_centered_circle,
        "circle": run_centered_circle,
        "takeoff_circle_land": run_takeoff_circle_land,
    }
    asyncio.run(command_runners[args.behavior](args))


if __name__ == "__main__":
    main()
