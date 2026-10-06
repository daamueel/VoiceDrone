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
- `SideCircle` and `CenteredCircle` assume the vehicle is airborne and never
  take off or land.
- Landing is an explicit runner action.

Future voice phrases such as "circle" and "centripetal" should resolve through
a command registry to one of these established circle behaviors without
changing trajectory code. A generic phrase needs a documented default or a
clarifying question because side and centered circles have different geometry.

The Step 8 implementation uses these small components:

- `voicedrone/trajectory.py`: PX4-independent trajectory and measured-state
  data types.
- `voicedrone/takeoff.py`: deterministic takeoff generation and completion.
- `voicedrone/side_circle.py`: circle with the airborne start on its
  circumference.
- `voicedrone/centered_circle.py`: radial entry followed by a circle centered
  on the airborne start.
- `voicedrone/px4_offboard_adapter.py`: the only MAVSDK/PX4 import boundary.
- `run_sitl.py`: wall-clock execution, action ordering, landing, and cleanup.
- `voicedrone/sitl_log.py` and `analyze_sitl.py`: CSV capture and analysis.

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

`SideCircle(radius=5.0)` and `CenteredCircle(radius=5.0)` default to 1 m/s
tangential speed, derive angular
velocity as `speed / radius`, and default to one revolution with duration
`2*pi/abs(angular_velocity)`. Explicit angular velocity and duration are
allowed subject to validation of invalid or conflicting inputs.

`SideCircle` initializes with the measured airborne position on its
circumference. For a selected phase, its centre is:

```text
Nc = start_N - R * cos(phase)
Ec = start_E - R * sin(phase)
```

Therefore, its first circular setpoint equals the measured start exactly. The
default phase is zero, so the centre is `radius` metres south of the start and
positive angular velocity initially moves east. The runner aligns yaw while
holding that first position before starting circular-motion time.

`CenteredCircle` stores the measured airborne start as its centre. Its entry
point is behind the initial heading, using `phase = initial_yaw - pi`. It moves
radially backward to the circumference while holding initial yaw, so its nose
faces the centre. Entry time and settling are separate from circular-motion
duration. The entry endpoint and first circle setpoint have identical position
and yaw.

Both circular segments hold starting altitude and command inward yaw:

```text
yaw = atan2(Ec - E, Nc - N)
yaw_rate = angular_velocity
```

Thus commanded yaw points exactly at the centre in either direction. The
physical vehicle follows with finite controller tracking error. PX4 receives
position/yaw setpoints; logged analytic velocity and yaw rate are not sent as
feed-forward.

The verified side circle uses radius 10 m and angular velocity 0.1 rad/s. The
verified centered circle uses radius 5 m and angular velocity 0.2 rad/s. Both
use 1 m/s tangential speed and one revolution.

## Command interface direction

`run_sitl.py` is the typed, validated behavior interface. Its command registry
currently dispatches `takeoff`, `circle-side`, and `circle-centered`. A future
text or voice parser should produce structured command names and numeric
arguments for that registry instead of invoking MAVSDK or shell commands
directly.

A separate SITL session manager can later launch PX4/Gazebo in WSL, wait for a
ready state, configure the Windows MAVLink route, execute one or more registry
commands, require landing and disarm, and shut the simulator down. Process
orchestration remains separate from trajectory generation and flight safety.

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
