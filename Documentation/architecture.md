# VoiceDrone architecture

## Milestone 1 boundary

Trajectory generation is pure Python. It accepts explicit trajectory time and
state and returns setpoints without importing PX4, MAVSDK, Gazebo, threading,
or wall-clock APIs. This keeps takeoff, circle geometry, completion, and frame
conversions deterministic and unit-testable.

A single PX4/MAVSDK adapter translates trajectory setpoints into offboard
commands and exposes measured vehicle state. The SITL runner owns connection,
arming, action order, logging, error handling, and safe shutdown. In particular:

- `Takeoff` climbs but does not select a later maneuver.
- `Circle` assumes the vehicle is airborne and never takes off or lands.
- Landing is an explicit runner action.

Future voice phrases such as "circle" and "centripetal" should resolve to the
same circle behavior without changing its trajectory implementation.

## Local frame conventions

Flight trajectories use PX4 local NED coordinates:

- `N` is north in metres.
- `E` is east in metres.
- `D` is down in metres, so climbing produces a more negative `D` value.
- The local position origin is PX4's estimator origin. Behaviors store the
  measured starting position as their operational reference rather than
  assuming it is exactly `(0, 0, 0)`.
- `Takeoff(target_altitude=5.0)` targets approximately 5 m above its measured
  starting reference altitude: `target_down = start_down - 5.0`.
- Yaw is in radians about the down axis, increasing clockwise when viewed from
  above: north is `0`, east is `+pi/2`.
- Yaw rate uses radians per second with the same positive-clockwise convention.

Any NED velocity converted to body FRD uses forward, right, down axes and the
vehicle's measured yaw. The conversion will be unit-tested at headings
`0`, `+pi/2`, `-pi/2`, and `pi`.

## Circle definition and safe entry

For circle centre `(Nc, Ec)`, radius `R`, phase `phase`, and trajectory time
`t`:

```text
theta = phase + angular_velocity * t
N = Nc + R * cos(theta)
E = Ec + R * sin(theta)
```

Positive angular velocity is clockwise when viewed from above; negative is
counter-clockwise. Tangential speed magnitude is
`abs(angular_velocity) * radius`.

`Circle(radius=5.0)` defaults to 1 m/s tangential speed, derives angular
velocity as `speed / radius`, and defaults to one revolution with duration
`2*pi/abs(angular_velocity)`. Explicit angular velocity and duration are
allowed subject to validation of invalid or conflicting inputs.

The circle will initialize from the measured airborne position. Its centre and
phase will be chosen so the first circular setpoint equals that position. If a
different entry geometry is needed, a separately timed entry maneuver will
reach the circumference first; entry time is not counted as circular-motion
duration. This prevents a position jump during the takeoff-to-circle handoff.

The SITL verification circle uses radius 10 m, angular velocity 0.1 rad/s,
speed 1 m/s, and approximately 62.83 seconds of circular motion.

## Telemetry artifacts

SITL runs will write generated artifacts under `logs/` using one shared UTC
timestamp and test name:

```text
sitl_<UTC-timestamp>_<test>.csv
sitl_<UTC-timestamp>_<test>_ne.png
```

Where available, CSV logs will contain commanded and measured NED position and
velocity, yaw, yaw rate, UTC timestamp, trajectory time, flight mode, and armed
state. Analysis will assess radius, speed, angular velocity, altitude, and yaw
behavior.
