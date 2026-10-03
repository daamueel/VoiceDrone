"""Run independently selectable VoiceDrone behaviors against PX4 SITL."""

import argparse
import asyncio
import time

from voicedrone.px4_offboard_adapter import PX4OffboardAdapter
from voicedrone.sitl_log import SitlLogger
from voicedrone.takeoff import Takeoff


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
                    print("Runner action: landing")
                    await adapter.land()
                    landing_started = time.monotonic()
                    while adapter.state().armed:
                        measured = adapter.state()
                        log.write(
                            time.monotonic() - landing_started,
                            "landing",
                            command,
                            measured,
                        )
                        await asyncio.sleep(0.1)
                    await adapter.wait_until_disarmed(timeout_s=5.0)
                    log.write(
                        time.monotonic() - landing_started,
                        "landing",
                        command,
                        adapter.state(),
                    )
                    print("Landing complete: vehicle disarmed")
            finally:
                await adapter.close()

    if not completed:
        raise RuntimeError("takeoff behavior did not complete")


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.behavior == "takeoff":
        asyncio.run(run_takeoff(args))


if __name__ == "__main__":
    main()
